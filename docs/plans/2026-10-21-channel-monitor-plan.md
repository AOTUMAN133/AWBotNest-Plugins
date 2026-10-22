# channel_monitor 实现计划

规格：`docs/superpowers/specs/2026-10-21-channel-monitor-design.md`

## 任务

### T1 纯逻辑层 `_core.py`

- `normalize_rules(raw)` → `[{source, target, enabled, src_key, dst_key}]`，解析失败的行丢弃并返回告警列表
- `match_rules(chat_id, rules)` → 命中的规则列表
- `compile_keywords(text)` / `passes_keywords(text, filename, kws)`
- `compile_filters` / `apply_filters`（移植自 channel_mover）
- `AlbumBuffer`：`add(msg) -> list|None`，`flush(group_key) -> list`
- `should_skip(msg_id, last_id)` 
- `render_status(rows)`

验收：`pytest tests/channel_monitor/test_core.py` 全绿。

### T2 发送层 `_sender.py`

- `forward_one(client, dst, msg_id, src_peer)` → 转发单条，`drop_author=True`
- `forward_album(client, dst, msg_ids, src_peer)` → `as_album=True`
- `with_flood_retry(coro_factory, max_wait)` → FloodWait 退避，超限抛 `Paused`
- 不设置 `silent`

验收：单测覆盖 FloodWait 分支与超限分支。

### T3 事件入口与状态机 `__init__.py`

- `@ctx.on_message(incoming=True)` 单参数 handler
- 按 chat_id 找规则 → 幂等判定 → 过滤 → 相册缓冲或直发 → 入队
- 每规则队列 + 单 worker，FIFO
- 状态落盘 `state:{src_id}`，每 20 条或 5 秒
- `teardown` 取消全部任务并落盘

验收：`test_flow.py` 假客户端走通。

### T4 补历史

- 先取最新 ID 设 `last_id`，再补 N 条（旧→新）
- 补期间实时事件入 pending，补完排空去重
- `backfill_count=0` 跳过

验收：`test_flow.py` 补历史用例。

### T5 命令

- `.chmon` / `.chmon test N` / `.chmon pause N` / `.chmon resume N`
- `incoming=False, outgoing=True`

验收：假事件单测。

### T6 仓库 pytest 配置

独立提交：根目录 `pytest.ini`，`asyncio_mode = auto`。

### T7 元数据与清单

- `__plugin__` 按规格第 4 节
- `manifest_v2.json` 增加 `channel_monitor` 条目
- 版本 `1.0.0`

## 约束

- 平台为 AWBotNest V2（Telethon），禁止任何 pyrogram/kurigram import
- 不修改 `plugins/channel_mover/` 任何文件
- `ctx.storage` / `ctx.kv` 全部 await
- 不吞 `CancelledError`
- 插件目录内不得放 `.gitignore`（平台 `_safe_path()` 规定路径任一段不得以 `.` 开头）
- 密钥不进源码/日志

## 完成标准

1. `pytest tests/channel_monitor` 全绿
2. `python -c "import ast; ast.parse(open(...).read())"` 通过
3. `__plugin__` 可被 AST 静态读取
4. `git status` 干净，提交信息含版本号
