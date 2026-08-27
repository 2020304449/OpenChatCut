# 技术设计 — 后端迁移 A-1（编辑核心 + Agent 循环 + 工具）

## 1. 核心架构决策：单体后端

OpenChatCut 的 Agent 运行时是「**服务端持 LLM 循环、浏览器持项目变更权威**」的分离架构——服务端从不直接改项目，每次工具调用都暂停，等浏览器「认领 → 执行 → 回填」（见 `research/agent-loop.md`）。

但 A-1 **没有前端/浏览器、没有 MCP**，所以这个分离在本阶段没有意义。本迁移采用**单体后端**：

```
FastAPI 后端 = LLM 循环 + 项目状态权威，工具直接改内存 store
```

- 简化理由：浏览器持权威是 Electron 架构的产物；阶段 B（Vue 前端）出现时再决定是否拆回「循环 / 权威分离」。
- **保留的语义**（迁移必须守住的契约，见 `research/agent-loop.md` §关键架构约束）：
  1. **工具 = 命令**：每个工具最终落到一条命令（1:1 契约，对齐 `tools-surface.md` 的映射总表）。
  2. 工具 schema 经注册表统一导出与校验。
  3. 编辑可追踪、可撤销（每条命令一个撤销节点）。

## 2. 目录结构

```
learning/openchatcut-backend/        # 新项目（与最小克隆并列，非覆盖）
  backend/
    requirements.txt
    pytest.ini
    app/
      domain/                        # 数据模型（frozen dataclass）
        __init__.py
        media.py       MediaAsset / MediaFolder
        track.py       Track / TrackFlags / TrackKind
        item.py        TimelineItem / ClipTransform / ZoomEffect / ClipEffect / Keyframe
        transition.py  TransitionItem
        marker.py      Marker
        captions.py    CaptionsData（简化）
        timeline.py    Timeline / TimelineState / ProjectDoc + to_dict
      commands/                      # 命令层
        __init__.py
        base.py        Command 协议 + Executor（撤销/重做）
        actions.py     38 种核心命令子集
      agent/
        __init__.py
        tools.py       工具 schema + execute（tool==command）
        registry.py    ToolRegistry（schema 导出 + 执行 + 校验）
        loop.py        多轮循环 + SSE 事件
      llm.py           OpenAI 兼容 + mock
      main.py          FastAPI 端点 + SSE
    tests/
      test_domain.py   序列化
      test_commands.py 命令 apply + undo/redo
      test_tools.py    工具 execute
      test_loop.py     mock 端到端
```

## 3. 数据模型（帧单位，frozen dataclass）

**关键决策：沿用帧单位**（`startFrame` / `durationInFrames` + `fps`），不换算秒，与源码一致，避免迁移换算错误。

**表示法**：领域状态用 `@dataclass(frozen=True)`（不可变，`dataclasses.replace` 做局部更新）；`to_dict` 负责序列化。Pydantic 只用于工具参数 schema 与 API 请求/响应 DTO（边界层）。

核心实体（字段对齐 `src/editor/{timelineTypes,clipTypes,trackTypes,projectTypes,transitionTypes,markerTypes}.ts`）：

| 实体 | 关键字段 |
|---|---|
| `ProjectDoc` | version, assets, mediaFolders, timelines, activeTimelineId, designStyle |
| `Timeline` | id, name, order, hidden, fps, width, height, fit, items, trackOrder, tracks, transitions, markers, captions, captionsHidden, selectedId, selectedIds |
| `TimelineItem` | id, track, startFrame, durationInFrames, name, **kind(9)**；可选 src/sourceAssetId/sourceFilename、templateId/code/props、volume、srcInFrame、fadeInFrames/fadeOutFrames、transform、keyframes、filters、zoom、effects、playbackRate |
| `Track` | id + flags(kind, name, hidden, muted, locked, collapsed, role) |
| `TransitionItem` | id, incomingItemId, transType, durationInFrames |
| `Marker` | id, name, frame/range, color |
| `CaptionsData` | 简化版：enabled, items[{startFrame, endFrame, text, speakerId}] |

- `kind` 枚举：`motion-graphic / audio / video / image / text / gif / svg / solid / sequence`。
- 文本稿字段（transcript/variants/gapCaps 等）**本阶段不建模**（Out of Scope）。

## 4. 命令层（38 种核心命令子集）

```python
class Command(ABC):
    def apply(self, state: ProjectDoc) -> ProjectDoc: ...
```

- 命令是不可变值对象；`Executor` 持有当前 `ProjectDoc` + `undo/redo` 栈。
- **撤销单位 = 命令节点**（一条命令一个撤销节点；`batch` 多操作合一撤销留待后续）。
- MVP 用**快照撤销**（已在最小克隆验证）；后续可升级为逆命令。

38 种命令子集（对应 `reducerActions.ts` Action type）：

| 类别 | 命令 |
|---|---|
| 轨道(4) | track.create / track.update / track.delete / toggleTrack |
| 片段基础(8) | add / remove / clear / duplicate / split / move / retime / updateProps |
| 片段属性(7) | setVolume / setFade / setTransform / setFilters / setSpeed / setZoom / setEffects |
| 转场(3) | addTransition / setTransition / removeTransition |
| 字幕(3) | setCaptions / updateCaptions / setCaptionsHidden |
| 关键帧(3) | setKeyframe / removeKeyframe / clearKeyframes |
| 标记(3) | addMarker / updateMarker / removeMarker |
| 选择(3) | select / selectMany / selectAll |
| 素材池(4) | addAsset / pool.createFolder / pool.moveAssets / pool.removeAsset |

- 命令作用域：`activeTimeline` 的时间线命令落到当前激活时间线；`pool.*` 落到素材池；与 `reducerActions.ts` 的 `projectReduce` 路由一致。

## 5. 工具层（tool == command）

```python
@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]     # Pydantic → model_json_schema()
    execute: Callable[[BaseModel, ToolContext], dict]
```

- 工具 schema 与 OpenChatCut 的 `AgentToolSchema`（`src/agent/tool-schema.ts`）同构。
- `ToolContext` 持有 `store`；`execute` 只做「校验参数 → 发命令 → 返回可读结果」。
- 工具粒度采用**细粒度「一命令一工具」**（`add_clip`/`move_clip`/`set_clip_volume`…），偏离 OpenChatCut 的 `edit_item` 复合工具 + `add_motion_graphic`/`add_audio`/`move_item` 等命名。这是刻意的教学取舍：细粒度让「tool == command」的 1:1 契约更直观；阶段 B 需要对齐真实工具面时再回改。
- 所有带 `itemId` 的编辑工具都做存在性校验：目标片段不存在时返回 `ok: False`，避免误导 LLM「报成功但无变化」。

实际实现 29 个工具（`app/agent/tools.py` 的 `TOOLS`）：

| 组 | 工具 |
|---|---|
| 只读(2) | read_timeline / read_project |
| 轨道(1) | edit_track（create/update/delete/toggle） |
| 片段基础(8) | add_clip / remove_clip / clear_timeline / duplicate_clip / split_clip / move_clip / set_clip_timing / update_clip_props |
| 片段属性(7) | set_clip_volume / set_clip_fade / set_clip_transform / set_clip_filters / set_clip_speed / set_clip_zoom / set_clip_effects |
| 转场(2) | add_transition / edit_transition |
| 字幕(1) | edit_captions |
| 关键帧(3) | set_keyframe / remove_keyframe / clear_keyframes |
| 标记(1) | manage_markers |
| 选择(1) | select_clips |
| 素材池(1) | manage_media_pool |
| 撤销(2) | undo_last_change / redo_last_change |

（延后：`read_captions`/`list_templates`/`probe_media` 等只读工具，以及生成类/导出类/web 抓取/run_code/音乐调色等，见 `research/tools-surface.md` 末尾。）

## 6. Agent 循环（`loop.py`）

```
system prompt(含当前时间线摘要 + 工具说明)
  → loop: llm.chat(messages, tools)
      ├─ tool_calls → 逐个执行 → 回填 result → 继续
      └─ 最终文本 → 结束
```

- 多轮无上限，但加 `MAX_ITER` 防呆（对齐最小克隆；OpenChatCut 无上限靠模型自停）。
- 事件流（SSE）：`state` / `tool_call` / `tool_result` / `assistant` / `error` / `done`。
- **自治验收简化**：OpenChatCut 有 acceptance 状态机（mutate 后必须 verify）；A-1 简化为「循环结束即完成」，验收状态机留待后续。
- LLM：`llm.py` 复用最小克隆思路——OpenAI 兼容（`LLM_BASE_URL/LLM_API_KEY/LLM_MODEL`）+ mock 模式（`LLM_MOCK`，无 Key 可跑）。

## 7. API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | SSE 流，body `{"message"}` |
| GET | `/api/state` | 当前 ProjectDoc JSON |
| GET | `/api/tools` | 工具 schema 清单 |
| POST | `/api/undo` / `/api/redo` | 撤销/重做 |
| GET | `/api/project` | 只读项目概览（read_project 用） |

## 8. 简化说明（迁移 vs 源码，刻意为之）

| 维度 | A-1 | OpenChatCut |
|---|---|---|
| 循环/权威 | 单体（后端持两者） | 分离（服务端循环 + 浏览器权威） |
| 撤销 | 快照撤销 | 细粒度逆命令 + batch/gesture |
| 验收 | 循环结束即完成 | 自治验收状态机 |
| 上下文 | 不做压缩 | 压缩 + checkpoint 持久化 |
| 持久化 | 内存态 | SQLite/IndexedDB sidecar |
| 流式 | 每轮 completion | token 级 streamText |
| 工具数 | ~20 | 120 edit + 22 ask |

## 9. 风险与回滚

| 风险 | 应对 |
|---|---|
| 帧单位 vs 秒混用 | 全程帧单位，`to_dict` 明确标注字段名含 Frame |
| 数据模型字段遗漏 | 以 `clipTypes.ts` 等源码为准，测试断言核心字段往返序列化 |
| 工具粒度选择偏差 | 对齐 OpenChatCut 实际工具名，后续补工具不破坏契约 |
| 范围蔓延（想加 MCP/渲染） | 严格 Out of Scope，后续独立任务 |
