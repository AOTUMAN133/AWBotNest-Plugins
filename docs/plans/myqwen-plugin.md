# myqwen 插件实现方案

> 基于 qwen2API (Go) 逆向工程，用 Python 实现 Qwen 网页版 API 的 AWBotNest 插件

**目标：** 创建一个类似 mydraw 的 AWBotNest 插件，支持通过 Qwen 账号免费文生图

**架构：**
- 逆向 Qwen Chat (chat.qwen.ai) 的 `/api/v2/` 接口
- 使用 Bearer token 认证（从 localStorage 提取）
- 通过 `t2i` (text-to-image) 模式调用 Qwen 图片生成
- 用 SSE 流式解析响应，提取图片 URL

**技术栈：** Python 3.11+, httpx, AWBotNest 插件框架

---

## Qwen API 核心端点和参数

### 1. 创建会话
```
POST https://chat.qwen.ai/api/v2/chats/new
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "api_<timestamp>",
  "models": ["qwen3.6-plus"],
  "chat_mode": "normal",
  "chat_type": "t2i",
  "timestamp": <unix_ts>
}
```
响应: `{"success": true, "data": {"id": "chat_id_xxx"}}`

### 2. 文生图对话（SSE 流式）
```
POST https://chat.qwen.ai/api/v2/chat/completions?chat_id=<chat_id>
Authorization: Bearer <token>
Content-Type: application/json
Accept: text/event-stream

{
  "stream": true,
  "version": "2.1",
  "incremental_output": true,
  "chat_id": "<chat_id>",
  "chat_mode": "normal",
  "model": "qwen3.6-plus",
  "parent_id": null,
  "messages": [{
    "fid": "<random_id>",
    "parentId": null,
    "childrenIds": ["<random_id>"],
    "role": "user",
    "content": "请生成图片...",
    "user_action": "chat",
    "files": [],
    "timestamp": <unix_ts>,
    "models": ["qwen3.6-plus"],
    "chat_type": "t2t",
    "feature_config": {
      "thinking_enabled": false,
      "output_schema": "phase",
      "auto_thinking": false,
      "thinking_mode": "off",
      "auto_search": false,
      "code_interpreter": false,
      "function_calling": false,
      "plugins_enabled": true,
      "image_generation": true,
      "default_aspect_ratio": "1:1"
    },
    "extra": {
      "meta": {
        "subChatType": "t2i",
        "mode": "image_generation",
        "aspectRatio": "1:1",
        "size": "1:1"
      }
    },
    "sub_chat_type": "t2i",
    "parent_id": null
  }],
  "timestamp": <unix_ts>,
  "size": "1:1"
}
```

### 3. 删除会话
```
DELETE https://chat.qwen.ai/api/v2/chats/<chat_id>
Authorization: Bearer <token>
```

### 4. SSE 响应格式
Qwen 返回 SSE 流，每行 `data: {...}`，关键字段：
- `choices[0].delta.content` — 文本内容，包含图片 URL
- 需要从内容中正则提取图片 URL

---

## 插件结构

```
plugins/myqwen/
├── __init__.py              # 主插件文件
├── _qwen_client.py          # Qwen API 客户端
├── _qwen_parser.py          # SSE 解析 + 图片 URL 提取
├── frontend/                # Vue 配置页
├── requirements.txt         # 依赖
└── manifest.json            # 插件清单
```

### 文件职责

#### `_qwen_client.py`
- `QwenClient` 类
- `create_chat(token, model, chat_type) -> str` — 创建会话
- `stream_chat(token, chat_id, payload) -> AsyncGenerator[dict]` — 流式对话
- `delete_chat(token, chat_id) -> bool` — 删除会话

#### `_qwen_parser.py`
- `parse_sse_events(response)` — 解析 SSE 流
- `extract_image_urls(content)` — 从内容中提取图片 URL
- `QwenSSEError` — 错误类型

#### `__init__.py`
- `.st <prompt>` — 文生图
- Token 配置（通过配置页或命令）
- 登录验证

---

## 工作流程

1. 用户配置 Qwen token（从 chat.qwen.ai 的 localStorage 获取）
2. 用户输入 `.st 一只柴犬`
3. 插件创建 Qwen 会话 (chat_type="t2i")
4. 发送文生图请求（含 image_generation feature）
5. 流式接收 SSE 响应
6. 从响应内容中提取图片 URL
7. 下载图片并发送给用户
8. 删除会话