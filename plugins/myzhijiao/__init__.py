# -*- coding: utf-8 -*-
# AWBotNest 插件：掷筊 (myzhijiao)

import random

__plugin__ = {
    "name": "掷筊",
    "id": "myzhijiao",
    "version": "1.1.2",
    "author": "凹凸曼",
    "description": "掷筊占卜，随机生成胜/阳/阴三筊并解读卦辞。用法: .zj",
    "scope": "user",
    "requirements": [],
}

TOSS_OPTIONS = ["圣杯", "笑杯", "阴杯"]
TOSS_SYMBOLS = {"圣杯": "☾☽", "笑杯": "☽☽", "阴杯": "☾☾"}

RESULT_MAP = {
    "圣杯": "圣杯（一阴一阳）：所求皆如意，吉星高照，万事亨通。上上大吉。",
    "笑杯": "笑杯（双阳）：好事多磨，须待时机，耐心守候，自有机缘。先难后易。",
    "阴杯": "阴杯（双阴）：诸事不宜，宜守不宜进，静待时机，切勿冲动。守旧待时。",
}


async def setup(ctx):
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=-18)
    async def _zj_handler(client, message):
        text = (message.text or "").strip()
        if text not in ("/zj", "/zhijiao"):
            return

        results = [random.choice(TOSS_OPTIONS)]
        result = results[0]
        symbol = TOSS_SYMBOLS[result]
        divination = RESULT_MAP.get(result, f"{result}：此卦无解，随缘即可。")

        reply = (
            f"🔮 <b>掷筊</b>\n\n"
            f"{symbol}  <code>{result}</code>\n\n"
            f"{divination}"
        )

        try:
            await client.send_message(message.chat.id, reply)
        except Exception:
            await client.send_message(message.chat.id, reply)


async def teardown(ctx):
    pass