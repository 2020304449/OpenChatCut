# 后端对齐原版 OpenChatCut

## 背景

当前 `learning/openchatcut-backend/` 是「学习用最小闭环」：单体 FastAPI 后端持有 `ProjectDoc` + `Executor` + LLM loop（78 命令 / 47 工具），前端 Vue3 是 SSE 薄客户端。现要对齐原版 OpenChatCut 的完整能力与架构，不再停留在学习 demo。

## 目标（用户已拍板的决策）

1. **架构对齐**：1:1 复刻原版「server 决策 / browser 权威」分离 + MCP 通信层（Streamable HTTP broker + claim/settle），不做简化协议。
2. **能力补齐**：18 个 DEFERRED 工具（mock 存根）+ 转写 ASR（faster-whisper）+ 导出（纯 FFmpeg）+ 媒体探测（ffprobe）+ SQLite KV 持久化。
3. **MCP 通信层纳入**（此前「后端不需要 mcp」的决定在架构对齐语境下撤销）。

## 研究基线

两轮 research 已落盘，作为 design 的事实依据：

- `08-28-backend-parity-arch/research/`：`arch-server-browser-split.md`、`mcp-broker.md`、`editor-core.md`
- `08-28-backend-parity-cd/research/`：`deferred-tools.md`、`asr-transcription.md`、`export-ffmpeg.md`、`media-probe.md`、`sqlite-persistence.md`

## 子任务与边界

### 子任务 A（`08-28-backend-parity-cd`）：能力补齐

在**现有单体架构内**填坑，不涉及 server/browser 分离：

- 18 个 DEFERRED 工具：mock 存根（schema + 幂等包装 + executor，返回假资产，验证契约与流程）
- 转写 ASR：faster-whisper（本地，词级毫秒时间戳）
- 导出：纯 FFmpeg 合成（拼接/转场/字幕/音频混流）
- 媒体探测：ffprobe（subprocess）
- SQLite：KV JSON 文档库（`sqlite3` stdlib）

### 子任务 B（`08-28-backend-parity-arch`）：架构对齐

把单体拆成原版的两端：

- server 决策 / browser 权威分离
- Streamable HTTP MCP broker（1:1 复刻 `queued → in_flight → applied/stale/cancelled/rejected/failed` 状态机 + 长轮询）
- claim/settle 协议（`/tool-claim` + `/tool-result` + SSE 事件流，三重防护 claimId/argsDigest/outcomeDigest）
- 前端持有 EditorCore（Vue3 版 `projectReduce` + 快照栈 undo/redo）
- autonomous acceptance 循环（mutation 后读复核）

## 关键架构约束

- **1:1 复刻 MCP 协议语义**（不是「思想对齐、协议简化」）
- 导出用纯 FFmpeg（明确放弃 Remotion 的 MG JSX / WebGL / GLSL 动效）
- 生成类工具 mock 存根（不接 DALL-E/TTS/音乐/视频付费 provider）
- 前端从薄 SSE 客户端升级为持有 EditorCore 权威

## 核心矛盾（design 必须解决）

「browser 权威」意味着 command → action → reducer 这条链要在**前端 TS 重实现**（原版 `executeTool → EditorCommands → projectReduce` 全在 browser）。这跟现有 Python 后端的 78 命令 / domain 层重复。

design 需在以下三条路线中定一条，并说明取舍：

1. 前端 TS 重实现 reducer（权威），Python 命令层降级为 offline 模式的 server-direct 执行路径。
2. 前端 TS 重实现 reducer（权威），Python 命令层保留作 offline/测试参考，双份维护。
3. 其他等价方案（需论证为何仍满足「browser 权威」）。

## 跨子任务验收标准

1. 能力补齐后：47+18 工具全部可执行（mock 存根工具返回可解析假资产），ASR/导出/探测有真实落地产物，SQLite 可重启恢复。
2. 架构对齐后：外部 MCP 客户端（如 Claude/Codex）能经 Streamable HTTP 连入，工具调用经 browser broker 执行并回传；undo/redo 在前端快照栈上正确。
3. 两子任务合并后，原版的两条链路（内部 server run 的 claim/settle、外部 MCP 的 broker）在 Python+Vue3 上等价成立。
