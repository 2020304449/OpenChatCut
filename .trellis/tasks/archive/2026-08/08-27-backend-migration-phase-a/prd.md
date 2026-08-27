# 后端迁移 A-1: 编辑核心 + Agent 循环 + 工具(核心子集, 无 MCP)

## Goal

把 OpenChatCut 的「编辑核心（不可变时间线 + 命令层）+ Agent 循环 + 工具面」迁移到 Python(FastAPI) 后端。**核心子集先行**：先迁核心数据模型 + 核心命令子集 + 核心工具子集 + 完整 Agent 循环，跑通「自然语言 → 工具调用 → 命令 → 可撤销状态」的完整后端闭环。**不含 MCP**，前端与渲染层不动。

用户价值：得到一个「架构正确、可扩展」的 Python 后端地基，之后可逐类补全剩余命令与工具。

## Requirements

### R1 — 数据模型（核心子集）
- 用 Pydantic / frozen dataclass 建模 OpenChatCut 的核心领域模型，**沿用帧单位**（`startFrame` / `durationInFrames` + `fps`），不改成秒。
- 必含：`ProjectDoc`（多时间线 + 素材池 + `activeTimelineId`）、`Timeline`（`fps/width/height/items/tracks/transitions/markers/captions/selection`）、`TimelineItem`（核心字段：`id/track/startFrame/durationInFrames/name/kind` + `volume/fade/transform/keyframes/filters/zoom/effects/playbackRate/src/sourceAssetId`）、`Track`（`kind/name/hidden/muted/locked/collapsed/role`）、`TransitionItem`、`Marker`、`CaptionsData`（简化版）。
- `kind` 覆盖 9 种：`motion-graphic/audio/video/image/text/gif/svg/solid/sequence`。

### R2 — 命令层（核心子集，~35 种）
- 命令 = 不可变状态 + 撤销栈。撤销单位为「命令」（对齐 OpenChatCut 的 `batch` 概念：一个撤销节点可含多个原子操作，MVP 可先按单命令一个撤销节点）。
- 核心命令子集（从 78 种 Action 中选）：
  - 轨道：`track.create / track.update / track.delete / toggleTrack`（4）
  - 片段基础：`add / remove / clear / duplicate / split / move / retime / updateProps`（8）
  - 片段属性：`setVolume / setFade / setTransform / setFilters / setSpeed / setZoom / setEffects`（7）
  - 转场：`addTransition / setTransition / removeTransition`（3）
  - 字幕：`setCaptions / updateCaptions / setCaptionsHidden`（3）
  - 关键帧：`setKeyframe / removeKeyframe / clearKeyframes`（3）
  - 标记：`addMarker / updateMarker / removeMarker`（3）
  - 选择：`select / selectMany / selectAll`（3）
  - 素材池：`addAsset / pool.createFolder / pool.moveAssets / pool.removeAsset`（4）

### R3 — 工具面（核心子集，对应 R2 的命令）
- 每个工具 = 参数 schema（Pydantic）+ `execute()`，execute 内部发命令。
- 工具面覆盖 R2 的每一类命令，数量与命令子集对应（约 20~30 个工具）。
- 工具清单可查询（API 暴露）。

### R4 — Agent 循环（完整）
- 多轮工具调用循环：LLM 返回 tool_call → 执行 → 结果回填 → 继续，直到最终文本。
- 支持 mock LLM（无 Key 可跑）+ OpenAI 兼容真实模型（环境变量配置）。
- SSE 流式输出事件（`state` / `tool_call` / `tool_result` / `assistant` / `done` / `error`）。

### R5 — API 与验证
- REST/SSE 端点：chat（流式）、state、tools、undo、redo、以及核心命令的只读/调试端点。
- pytest 覆盖：数据模型序列化、命令 apply、撤销/重做、工具 execute、mock 循环端到端。

## Acceptance Criteria

- [ ] 数据模型能无损表达「多时间线 + 多轨 + 片段 + 转场 + 字幕 + 标记 + 关键帧」的核心结构，且有 `to_dict` 序列化。
- [ ] 核心命令子集（R2 的 ~35 种）每种都有 apply 实现 + 至少一条 pytest 断言。
- [ ] 撤销/重做正确（对齐 OpenChatCut：撤销回退到上一个命令节点）。
- [ ] 工具面覆盖 R2 全部命令类别，`GET /api/tools` 返回对应 schema。
- [ ] mock LLM 下一句含「加片段 + 转场 + 字幕」的指令，能产生对应 tool_call 序列，最终时间线反映这些改动。
- [ ] 配置真实 LLM 后同样跑通（OpenAI 兼容）。
- [ ] SSE 事件序列正确，`undo` 回退最近命令。

## Out of Scope

- MCP server、外部 Agent 入口
- 文本稿词级编辑（`setItemTranscript/toggleWord/deleteWords/cleanScript/setGapCap/reorderTrackItems/clearEdits/fixTranscriptWord/renameSpeaker`）
- 多机位（`multicam`）、链接组（`linkGroups`）、AI 降噪（`setItemDenoise`）、reframe 关键帧、水印（`updateWatermark`）、背景填充（`setBackgroundFill`）、`setFullState`
- 前端 UI、渲染（Remotion/WebGL）、导出（FFmpeg/FCPXML/SRT）
- 磁盘持久化（MVP 内存态即可）

## Key Decisions

- 后端 Python + FastAPI（AI 生态兼容性）。
- **沿用帧单位**（不换算秒），与 OpenChatCut 源码一致，避免迁移时换算错误。
- 撤销单位对齐「命令节点」，MVP 先用快照撤销（已在最小克隆验证），后续可升级为逆命令。
- 工具 schema 用 Pydantic `model_json_schema()`，对齐 `src/agent/tool-schema.ts` 的 `AgentToolSchema`。
- LLM 走 OpenAI 兼容 + mock 模式（复用最小克隆 `llm.py` 思路）。

## Notes

- 完整命令面 78 种（`src/editor/reducerActions.ts`）、工具文件 101 个、编辑核心 102 个文件——本任务只迁核心子集，其余按需补全。
- 数据模型与命令面的精确字段以 `src/editor/{clipTypes,timelineTypes,trackTypes,transitionTypes,projectTypes}.ts` 为准，已在 design.md 记录。
