# C+D 能力补齐：DEFERRED 工具 + 服务层 + SQLite

## 背景

迁移版现有 47 工具，其中 18 个生成/导出类工具在 `tools.py` 的 `DEFERRED_TOOLS` 标记未实现；服务层（转写/导出/探测）未接真实能力；持久化是 JSON 文件快照。本子任务在**现有单体架构内**补齐这些，不涉及 server/browser 分离（那是 arch 子任务）。

研究基线：`research/deferred-tools.md`、`asr-transcription.md`、`export-ffmpeg.md`、`media-probe.md`、`sqlite-persistence.md`。

## 需求

### 1. 18 个 DEFERRED 工具（mock 存根）

对齐原版「schema + 幂等包装 + executor」三层结构，但生成/导出走 **mock 存根**（不接付费 provider、不做 Remotion 渲染），验证契约与流程。

**同步/异步分界**（对齐原版）：
- 同步（立即返回资产）：`submit_image`、`submit_voice`、`submit_sound`(elevenlabs)
- 异步（返回 `jobId`，配 `track_progress` / `rerun_generation`）：`submit_sound`(sonilo)、`submit_music`、`submit_video`

**契约要求**：
- 返回结构含原版的 `jobId` / `renderId` / `operationId` / `addedTo` 约定
- `submit_image`/`submit_voice` 返回 `{ ok, generated/assetId, name, src, ... addedTo }`
- 异步生成类返回 `{ ok, ...submission, next:"Call track_progress ... jobIds=<jobId>" }`
- `track_progress` 支持 `action=status/wait`，能查到 mock job 的状态
- `rerun_generation` 按 `jobId` 重跑
- 幂等：`generationIdempotencyKey`；durable generation tool（`reserveGenerationOperation` 的等价物）要求 projectId，缺省报 `generation_project_required`
- 导出类：`submit_export`（同步）、`submit_render_job`（异步返回 `renderId`）、`track_export`（status/wait）、`verify_export`（QA 报告）

**mock 存根语义**：返回可解析的假资产（`assetId`/`name`/`src`/`width`/`height`/`durationInFrames`），异步 job 有可查询的 mock 状态机（`pending → completed`），让 agent 循环能完整跑通「提交 → 查进度 → 取结果」。

### 2. 转写 ASR（faster-whisper）

- `transcribe_track` 命令从「未实现」改为调用后端真实转写服务。
- 引擎：本地 `faster-whisper`（对齐原版「本地 whisper」路径，而非浏览器 transformers.js）。
- 产出结构对齐 `TranscriptWord{ text, startMs, endMs, speaker? }`（毫秒时间戳），经 `SetItemTranscript` 写回片段。
- 轨道过滤：只转写有 `src` 的 audio/video 片段，已有有效 transcript 的跳过。
- `no-audio` 视为跳过而非失败。

### 3. 导出（纯 FFmpeg）

对齐原版的「时间线 → 产物」契约，但渲染引擎用**纯 FFmpeg**（明确放弃 Remotion 的 MG JSX / WebGL / GLSL 动效）。

- 视频：h264 → `.mp4`；vp8 → `.webm`
- 音频：mp3 / wav
- 字幕：srt / txt（纯文本导出，不走渲染）
- 工程 XML：fcpxml（纯文本导出）
- 帧范围半开 `[startFrame, endFrameExclusive)`
- 异步渲染走 `submit_render_job`（返回 `renderId`）+ `track_export`（`downloadUrl` + 状态）

### 4. 媒体探测（ffprobe）

- 本地 ffprobe（对齐原版 `media-normalization.ts` 的 `probeVideo` 层，而非 e2b 沙箱路径）。
- 字段：`width`/`height`/`duration`/`videoCodec`/`audioCodec`/`hasAudio`/`avgFrameRate`/`nominalFrameRate`/`frameCount`/`variableFrameRate`（旋转流交换宽高）。
- `probe_media` 工具降级为本地 ffprobe 等价实现，返回 `{ ok, source, durationSeconds, width, height, fps, hasVideoTrack, hasAudioTrack, videoCodec, audioCodec, qualityRisks }`。

### 5. SQLite KV 持久化

- 用 `sqlite3` stdlib 实现 key-value JSON 文档库（对齐原版 `kv(k,v)` 单表，非关系型）。
- 键命名空间：`project:<id>`（完整 ProjectDoc JSON 快照）、`generation-jobs:snapshot`、`deleted-projects:v1`。
- 迁移：现有 `persist.py` 的 JSON 文件 → SQLite，带权威迁移标记（`storage_migration_state` 的等价物）。
- WAL 模式、`BEGIN IMMEDIATE` 事务。
- FTS5 全文索引 / vec0 语义向量**延后**（本子任务不做，属搜索增强）。

## 验收标准

1. 47 + 18 = 65 工具全部可在 agent 循环里执行；mock 生成类返回可解析假资产，异步 mock job 能被 `track_progress` 查到终态。
2. `transcribe_track` 对本地音频产出词级毫秒 `TranscriptWord`，并经 `SetItemTranscript` 落到片段。
3. 导出：一条含多片段/转场/字幕的时间线能导出 `.mp4`/`.srt`，产物可被 ffprobe 读到正确时长/分辨率。
4. `probe_media` 对本地媒体文件返回结构化探测结果。
5. SQLite 重启后能恢复完整 ProjectDoc；从 JSON 迁移不丢数据；幂等（重复迁移不重复导入）。
6. 现有 66 个 pytest 全绿；新增服务层/工具/SQLite 测试覆盖。
