import json
import re
import aiohttp


async def doubao_image_parse(url: str, return_raw: bool = False):
    """从豆包对话链接中提取无水印图片URL"""
    if "doubao.com/thread/" not in url:
        raise ValueError("链接格式不正确，请使用豆包对话链接（包含 /thread/）")

    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                html_str = await response.text()
    except aiohttp.ClientError as e:
        raise ValueError(f"网络请求失败，请检查网络连接: {e}")

    match_json_str = None
    match_pattern = [
        'data-script-src="modern-run-router-data-fn" data-fn-args="(.*?)" nonce="',
        'data-script-src="modern-run-window-fn" data-fn-name="mergeLoaderData" data-fn-args="(.*?)" nonce="',
    ]
    for pattern in match_pattern:
        match_json_str = re.search(pattern, html_str, re.DOTALL)
        if match_json_str:
            break

    if not match_json_str:
        raise KeyError("无法解析页面数据，请确认链接是否有效")

    try:
        json_str = match_json_str.group(1).replace("&quot;", '"')
        json_data = json.loads(json_str)
        if return_raw:
            return json_data

        image_list = []
        for data in json_data:
            if isinstance(data, dict) and data.get("data"):
                message_snapshot = data["data"]["message_snapshot"]["message_list"]
                for message in message_snapshot:
                    if not message.get("content_block"):
                        continue

                    for m2 in message["content_block"]:
                        if m2.get("content_v2"):
                            json_data2 = json.loads(m2["content_v2"])
                        else:
                            json_data2 = json.loads(m2["content"]) if isinstance(m2["content"], str) else m2["content"]

                        if not json_data2.get("creation_block"):
                            continue
                        creations = json_data2["creation_block"]["creations"]

                        for image in creations:
                            image_raw = image["image"]["image_ori_raw"]
                            image_raw["url"] = image_raw["url"].replace("&amp;", "&")
                            image_list.append(image_raw)

            elif isinstance(data, list) and data:
                router_data_fn = json.loads(data[0]["routerDataFnArgs"][0])
                message_snapshot = router_data_fn["data"]["message_snapshot"]["message_list"]
                for message in message_snapshot:
                    if not message.get("content_block"):
                        continue

                    for m2 in message["content_block"]:
                        json_data2 = m2.get("content_v2") or m2.get("content")
                        json_data2 = json.loads(json_data2) if isinstance(json_data2, str) else json_data2

                        if json_data2.get("creation_block"):
                            creations = json_data2["creation_block"]["creations"]
                            for image in creations:
                                image_raw = image["image"]["image_ori_raw"]
                                image_raw["url"] = image_raw["url"].replace("&amp;", "&")
                                image_list.append(image_raw)

    except KeyError as e:
        raise KeyError(f"页面结构发生变化，无法解析图片数据: {e}")
    except json.JSONDecodeError:
        raise ValueError("页面数据格式错误，无法解析")

    return image_list


async def doubao_video_parse(url: str, return_raw: bool = False):
    """从豆包视频分享链接中提取无水印视频URL"""
    if "doubao.com/video-sharing" not in url:
        raise ValueError("链接格式不正确，请使用豆包视频分享链接（包含 /video-sharing/）")

    headers = {
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                html_str = await response.text()
    except aiohttp.ClientError as e:
        raise ValueError(f"网络请求失败，请检查网络连接: {e}")

    match_json_str = None
    match_pattern = [
        'data-script-src="modern-run-router-data-fn" data-fn-args="(.*?)" nonce="',
    ]
    for pattern in match_pattern:
        match_json_str = re.search(pattern, html_str, re.DOTALL)
        if match_json_str:
            break

    if not match_json_str:
        raise KeyError("无法解析页面数据，请确认链接是否有效")

    try:
        json_str = match_json_str.group(1).replace("&quot;", '"')
        json_data = json.loads(json_str)
        if return_raw:
            return json_data

        video_list = []
        for data in json_data if isinstance(json_data, list) else [json_data]:
            if isinstance(data, dict) and data.get("data"):
                message_snapshot = data["data"]["message_snapshot"]["message_list"]
                for message in message_snapshot:
                    if not message.get("content_block"):
                        continue
                    for m2 in message["content_block"]:
                        content = json.loads(m2.get("content_v2") or m2.get("content", "{}"))
                        if not content.get("creation_block"):
                            continue
                        for creation in content["creation_block"]["creations"]:
                            if creation.get("video"):
                                video_info = {
                                    "url": creation["video"].get("video_ori_raw", {}).get("url", ""),
                                    "cover_url": creation["video"].get("video_cover", {}).get("url", ""),
                                    "duration": creation.get("duration", 0),
                                }
                                video_info["url"] = video_info["url"].replace("&amp;", "&")
                                video_list.append(video_info)
    except (KeyError, json.JSONDecodeError) as e:
        raise KeyError(f"无法解析视频数据: {e}")

    return video_list