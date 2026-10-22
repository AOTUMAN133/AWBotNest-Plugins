# 频道监控转发（channel_monitor）设计规格

- 日期：2026-10-21
- 状态：待实现
- 参考实现：`plugins/channel_mover`（历史搬运，驱动模型不同，仅复用发送层与纯逻辑）

## 1. 目标

把源频道/群**新产生**的消息实时转发到目标群。支持多条「源 → 目标」规则，支持在插件启用时先补最近 N 条历史，避免上线瞬间漏消息。

## 2. 非目标（明确不做）

| 不做 | 原因 |
|---|---|
| 保留回复关系 | Telethon 服务端转发 `forward_messages` 无 `reply_to` 参数，做不到。不提供假开关。 |
| 同步编辑/删除 | 源频道改动不回溯到目标群。 |
| 原生转发头（带「转发自」） | 只保留 `drop_author=True` 一种复制语义，减少配置项。 |
| 全量历史搬运 | 由 `channel_mover` 负责，本插件不重复实现。 |

## 3. 目录结构

```
plugins/channel_monitor/
  __init__.py    元数据 / setup / 事件入口 / 命令 / 补历史编排
  _core.py       纯逻辑：规则匹配、关键词与正则过滤、相册缓冲、去重判定、状态文本
  _sender.py     发送层：单个/相册转发、FloodWait 退避、失败计数
tests/channel_monitor/
  test_core.py   纯逻辑单测
  test_flow.py   假客户端全流程
```

`_core.py` / `_sender.py` 从 `channel_mover` 移植，但修掉两个缺陷：

1. 不再设置 `silent=True`（原 `_tcall` 里设置后导致消息被静音）
2. `skipped` 计数真实累加（原实现只初始化、从不 `+=`）

`channel_mover` 的任何文件不得修改。

## 4. 元数据

```python
__plugin__ = {
    "id": "channel_monitor",
    "name": "频道监控转发",
    "version": "1.0.0",
    "scope": "user",
    "plugin_api_version": 2,
    "author": "凹凸曼",
    "description": "实时监控多个源频道，把新消息转发到对应目标群，支持相册、关键词过滤、启用时补历史。",
    "tags": ["监控", "转发", "频道", "同步"],
    "resources": {
        "timeout_seconds": 120,
        "max_concurrency": 8,
        "max_background_tasks": 32,
        "failure_threshold": 10,
        "recovery_seconds": 30,
    },
    "config_schema": { ... },   # 见第 6 节
}
```

## 5. 配置项

### 转发规则

`rules`（`list`）每行三个字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `source` | string | 源频道。支持 `@username`、`t.me/xxx`、`t.me/c/xxx`、`-100xxx` |
| `target` | string | 目标群。同上，且账号必须已在群内 |
| `enabled` | boolean | 默认 true。关掉则本行不参与匹配 |

行内使用字符串而非 `chat` 选择器：`chat` 选择器在多行 `list` 中的行为未经验证，字符串配合 `resolve_peer()` 归一化足够。

### 补历史

| 字段 | 类型 | 约束 | 默认 | 说明 |
|---|---|---|---|---|
| `backfill_enable` | boolean | — | true | 启用/重载时是否补历史 |
| `backfill_count` | number | 0 ~ 5000 | 20 | **由用户自行设置**补多少条。填 0 = 不补。从旧到新发送 |

### 内容

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `copy_media` | boolean | true | 关=只转文字 |
| `keep_albums` | boolean | true | 关=相册拆成单条 |
| `attach_source` | boolean | false | 开=在文字/说明末尾追加一行原消息链接 |

### 过滤

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `keywords` | text | "" | 每行一个词，命中任一即转发。留空=全转 |
| `drop_regex` | text | "" | 每行一条 Python 正则，命中文字或文件名则跳过 |
| `replace_regex` | text | "" | 每行 `原正则\|替换内容` |
| `skip_service` | boolean | true | 跳过入群/退群/置顶等系统消息 |

### 速率

| 字段 | 类型 | 约束 | 默认 | 说明 |
|---|---|---|---|---|
| `album_window` | slider | 0.3 ~ 3.0 | 0.8 | 相册合并窗口（秒） |
| `flood_wait_max` | number | 10 ~ 3600 | 300 | 超过则暂停该规则并通知 |

### 命令

| 字段 | 类型 | 默认 |
|---|---|---|
| `command` | string | `/chmon` |

`/chmon` 与 `.chmon` 等价。

## 6. 数据流

```
on_message(incoming=True)
  │
  ├─ event.chat_id 归一化 → 在规则表里找匹配规则（可能命中多条）
  ├─ 幂等：event.id <= state.last_id → 丢弃（防断线重连重推）
  ├─ 过滤：系统消息 / keywords 不匹配 / drop_regex 命中 → 丢弃并计入 skipped
  ├─ 有 media_group_id → 进缓冲池，album_window 后整组发送
  │    无 → 立即发送
  ├─ 发送：client.forward_messages(dst, [ids], from_peer=src, drop_author=True)
  │    相册：as_album=True 一次性整组
  └─ 落盘 last_id（每 20 条或每 5 秒一次，二选一先到）
```

### 相册缓冲

Telethon 把相册成员逐条推送，平台不提供整组事件。缓冲池键为 `(source_id, media_group_id)`，首个成员到达时启动 `album_window` 定时器，到期后整组发送。

窗口必须容得下相册所有成员到达（Telethon 实测通常在 1 秒内推完，窗口取 0.8 秒起步；用户可调到 3 秒）。

### 幂等

每个源持久化 `state:{source_id} = {last_id, sent, skipped, failed, id_map?}`。`event.id <= last_id` 一律丢弃。

这是必需的：Telethon 在断线重连、`catch_up` 后可能重推已处理的消息。

### 发送顺序

每条规则一个有界队列 + 单个 worker 任务。同一规则内严格 FIFO；不同规则之间并行。

FloodWait：`seconds <= flood_wait_max` 时等待后重试同一条；超过则暂停该规则，`ctx.notify` 告警，等用户 `.chmon resume N`。

## 7. 补历史时序

顺序是硬要求，反过来会重复转发：

```
1. 启动时为每条规则取源频道最新一条消息 ID → state.last_id = 该 ID
2. 再补最近 N 条（ID < last_id），从旧到新发送
3. 补的同时，实时事件照常进入队列，但只入队不发送（pending 模式）
4. 补完 → 排空队列，按 id > last_id 去重后发送
5. 转入正常实时
```

第 1 步先设 `last_id` 是关键：这样补历史期间到达的新消息（id > last_id）不会被去重逻辑误杀，也不会在补完后重复发送。

`backfill_count = 0` 或 `backfill_enable = false` 时跳过第 1~4 步，只做第 1 步设 `last_id`。

## 8. 命令

| 命令 | 作用 |
|---|---|
| `.chmon` | 所有规则状态表：源、目标、最近转发 ID、成功/跳过/失败数、运行状态 |
| `.chmon test <序号>` | 连通性自检：能否取到源频道、能否向目标群发送（发一条测试文本） |
| `.chmon pause <序号>` | 暂停该规则（保留 last_id，恢复后不补发） |
| `.chmon resume <序号>` | 恢复该规则 |

命令必须由自己发出：`@ctx.on_message(incoming=False, outgoing=True)`。

## 9. 错误处理

| 场景 | 处理 |
|---|---|
| 规则里源/目标解析失败 | 加载时跳过该行，日志告警，状态表标红，不影响其他规则 |
| 取不到源频道（没加入/被封） | 该规则标记为「不可达」，定时重试（5 分钟） |
| 目标群禁言/无权限 | 该规则暂停并 `notify` 告警 |
| 单条转发失败 | `failed += 1`，记录消息 ID，继续下一条（不阻塞队列） |
| FloodWait | 见第 6 节 |
| `CancelledError` | 必须继续抛出，不得吞掉 |
| 插件停用 | `teardown` 取消所有 worker 与定时器，落盘状态 |

## 10. 测试标准

**纯逻辑单测（`test_core.py`）**

- 规则匹配：同一 chat_id 命中多条规则 / 归一化后匹配（`@name` vs `-100xxx`）
- 关键词：任一命中即通过；留空全通过；大小写不敏感
- 正则丢弃与替换
- 相册缓冲：同一 `media_group_id` 归组；不同组不串；无 `media_group_id` 走单条
- 去重判定：`id <= last_id` 返回丢弃
- 状态文本渲染

**全流程（`test_flow.py`，假客户端）**

- 3 条普通消息 + 1 个 3 张图的相册 → 目标收到 4 次调用，相册那次是 `as_album=True` 且带 3 个 ID
- 补历史：`backfill_count=5` → 补发 5 条、`last_id` 等于当前最新 ID、期间到达的实时消息不重复
- 停用后无残留任务

## 11. 验收

- `pytest tests/channel_monitor` 全绿（仓库需补 `asyncio_mode=auto` 配置，见下）
- 平台启用后 `.chmon test 1` 通过
- 真实源频道发 1 条文字 + 1 个相册 → 目标群各收到 1 条
- 重载插件后不重复转发已转过的消息

## 12. 附带修复（独立提交）

仓库目前缺 pytest 配置，直接 `pytest` 会因 `asyncio_mode` 未设导致 27 个用例报错。补一个最小 `pytest.ini`：

```ini
[pytest]
asyncio_mode = auto
```

该修复与插件无关，单独提交，避免混在插件提交里。
