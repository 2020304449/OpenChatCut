# 技术设计 — 后端迁移 A-3

## A 类：数据模型增量

### multicam / linkGroups 字段

```python
# domain/multicam.py（新）
@dataclass(frozen=True)
class TimelineLinkGroup:
    id: str
    itemIds: tuple[str, ...]
    anchorItemId: str
    mode: str          # 'linked' | 'sync-lock'

@dataclass(frozen=True)
class MulticamAngle:
    id: str
    itemId: str
    label: str
    offsetFrames: int = 0
    confidence: float = 1.0

@dataclass(frozen=True)
class MulticamAngleDecision:
    id: str
    fromFrame: int
    toFrame: int
    angleId: str

@dataclass(frozen=True)
class MulticamGroup:
    id: str
    referenceAngleId: str
    masterAngleId: str
    angles: tuple[MulticamAngle, ...] = ()
    syncMethod: str = 'source-timecode'
    decisions: tuple[MulticamAngleDecision, ...] = ()
```

- `Timeline` 加 `linkGroups: tuple[TimelineLinkGroup, ...] = ()`、`multicamGroups: tuple[MulticamGroup, ...] = ()`
- `TimelineItem` 加 `multicamGroupId: str | None = None`、`multicamAngleId: str | None = None`

### 命令

| 命令 | apply |
|---|---|
| TrackTighten(track) | 同轨道 item 按 startFrame 排序后，从 0 紧凑排列 |
| SetCanvas(width, height, fit) | 改 activeTimeline 的 width/height/fit |
| SetMulticamGroups(groups) | 替换 Timeline.multicamGroups |
| AddMulticamDecision(group_id, from_frame, to_frame, angle_id) | 追加切机决策 |
| SetLinkGroups(groups) | 替换 Timeline.linkGroups |
| AddLinkGroup(group) | 追加联动组 |

## B 类：工程化设计

### B1 LLM 重试（llm.py）

```python
TRANSIENT_CODES = {'rate_limit', 'timeout', 'server_error', 'connection_error'}
for attempt in range(3):
    try: return self._chat_once(...)
    except OpenAIError as e:
        if not is_transient(e) or attempt == 2: raise
        sleep(0.5 * 2 ** attempt)   # 500ms → 1s → 2s
```

### B2 token 流式（llm.py + loop.py）

`stream_chat(messages, tools) -> Iterator[dict]`，yield：
- `{"type": "text", "delta": "..."}`（token 增量）
- `{"type": "tool_calls", "calls": [ToolCall...]}`（一轮工具调用）
- `{"type": "done"}`

- 真实：OpenAI `stream=True`，遍历 chunk，tool_calls 需要跨 chunk 累积。
- mock：yield 一个 `text`（整段）+ `tool_calls`（逐条）+ `done`。
- loop.py：消费流，text delta → `assistant` 事件；tool_calls → 执行后继续下一轮流。

### B3 自治验收（loop.py）

- 记录 `mutated`：本轮是否执行了非 read 工具。
- 循环自然结束（无 tool_calls）且 `mutated` 时，注入一条用户消息「请用 read_timeline/read_project 验证最新时间线状态后再总结」，再跑一轮；若该轮是纯读，正常收尾。

### B4 上下文压缩（loop.py）

- `estimate_tokens(messages)`：`sum(len(serialize(m))) // 4`。
- 超过阈值（如 12000）时：保留 system + 最近 6 条，中间替换为一条摘要消息「（前文已压缩）」。

### B5 run 持久化（persist.py）

```python
def load_project(path) -> ProjectDoc | None   # JSON → dataclass
def save_project(doc, path) -> None           # dataclass → JSON
```

- 序列化复用 `project_to_dict` / 一个 `project_from_dict`（手写反序列化，因为 dataclass 嵌套）。
- main.py 用 FastAPI `lifespan` 在启动 load、关闭 save；默认路径 `data/project.json`（可用 `OPENCHATCUT_DATA_DIR` 覆盖）。

## 风险

- B2 流式改造改动 loop.py 核心循环，需保证 mock 与真实 LLM 行为一致 → 用同一接口 + 单测两种后端。
- B4 启发式 token 估算对中文偏差大 → 阈值留余量（12000 远低于真实 32k+）。
- B5 反序列化要处理 `project_from_dict` 的字段缺失 → 用默认值兜底。
