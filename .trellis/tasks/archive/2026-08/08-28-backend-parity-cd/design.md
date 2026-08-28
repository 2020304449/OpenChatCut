# C+D 能力补齐 design

## 设计总则

在现有单体架构内填坑，不引入 server/browser 分离。复用现有 `Tool`（name/description/args_model/execute）、`ToolContext`（持有 executor）、`build_registry` 结构。服务层（ASR/导出/探测）作为独立模块被工具调用，SQLite 替换 `persist.py` 的 JSON 快照。

## 1. 18 个工具 mock 存根

### 结构

沿用 `tools.py` 的 `Tool` 三层：schema（args_model 是 Pydantic，自动出 JSON schema）→ 幂等包装 → mock executor。

新增 `backend/app/agent/mock_generation.py`，集中放 mock executor 与 mock job store。

### 同步 / 异步分界（对齐原版契约）

| 类别 | 工具 | mock 行为 |
|---|---|---|
| 同步生成 | `submit_image`/`submit_voice`/`submit_sound`(elevenlabs) | 生成假资产 → `AddAsset` → 返回 `{ok, assetId, name, src, addedTo}` |
| 异步生成 | `submit_sound`(sonilo)/`submit_music`/`submit_video` | 生成 `jobId` + 注册 mock job → 返回 `{ok, next:"Call track_progress ... jobIds=<jobId>"}` |
| 进度 | `track_progress` | 查 mock job store，`action=status` 立即返回，`wait` 直接给终态 |
| 重跑 | `rerun_generation` | 按 `jobId` 重新注册一个 mock job |
| 动效 | `submit_motion_graphic`/`create_motion_graphic_from_code`/`submit_shader` | 生成假 motion-graphic/shader 资产 |
| 导出 | `submit_export`(同步)/`submit_render_job`(异步返回 `renderId`)/`track_export`/`verify_export`/`export_motion_graphic_prores`/`convert_motion_graphic_to_video`/`register_converted_video`/`export_jianying_draft` | 导出类走 §3 的 FFmpeg 真实导出（非纯 mock）；MG→video 类 mock 返回假资产 |

### mock job store

- `MockJobStore`：进程内 `dict[jobId -> {status:'pending'|'completed', result, createdAt}]`，全局单例。
- 异步工具注册 job 返回 `jobId`；`track_progress`/`track_export` 查它。
- 幂等：`generationIdempotencyKey` 参数存在时，同一 key 重复调用返回同一 job/资产，不重复生成。
- durable 工具（`submit_music`/`submit_video`/`submit_sound`）要求 `projectId` 存在，缺省返回 `generation_project_required`。

## 2. 转写 ASR（faster-whisper）

- 新依赖 `faster-whisper`（CTranslate2 后端）。Windows 下 `ctranslate2` 需在 `requirements.txt` 声明。
- 新增 `backend/app/services/transcription.py`：
  - `transcribe_audio(path) -> list[TranscriptWord]`，`WhisperModel` 懒加载（首次调用才加载，模型默认 `base`，可 `OPENCHATCUT_WHISPER_MODEL` 覆盖）。
  - 词级时间戳：`segments` → `word.start`/`word.end`（秒）→ 乘 1000 取整得 `startMs`/`endMs`。
  - `TranscriptWord{text, startMs, endMs, speaker?}`（speaker 置 None，对齐无 diarization 路径）。
- `transcribe_track` 工具（从 DEFERRED 移除）：过滤轨道上 `kind in {audio,video}` 且 `src` 非空的片段，逐个转写，`SetItemTranscript` 写回。无音频（空结果）跳过。
- 转写是耗时阻塞，run 在同步 executor 里串行（与现有命令一致，不引入异步）。

## 3. 导出（纯 FFmpeg）

- 新增 `backend/app/services/export.py`：
  - `render_timeline(timeline, out_path, format, ...)`：把 Timeline 数据转成 `ffmpeg -filter_complex` 命令。
  - 视频：按 `trackOrder` 对每个轨道 clip 做 `-i` 输入，用 `overlay`/`concat` + `xfade` 转场组装；字幕轨用 `subtitles` filter（先导出 `.srt`）或 `drawtext`。
  - 音频：`amix` 混流各音频轨。
  - 输出：h264→`.mp4`、vp8→`.webm`、mp3/wav。
  - 帧范围半开 `[startFrame, endFrameExclusive)` → 用 `-ss`/`-t` 或 trim。
- 字幕导出（`submit_export format=subtitles`）：`captionCues` → SRT 纯文本（`services/subtitles.py`），不走 FFmpeg。
- XML 导出（`format=xml`）：timeline → FCPXML 纯文本（`services/fcpxml.py`），首版最小实现（标注字段对齐原版契约，完整度延后）。
- FFmpeg 二进制：`ffmpeg` 需在 PATH，或 `OPENCHATCUT_FFMPEG` 覆盖（对齐原版 `ffmpegBin()` 解析链）。
- 异步导出：`submit_render_job` 注册 render job 到 `MockJobStore`，`track_export` 查状态（真实渲染可后台线程执行，首版同步完成立即置 `completed`）。

## 4. 媒体探测（ffprobe）

- 新增 `backend/app/services/probe.py`：`probe_media(path) -> ProbeResult`，`subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",path])`。
- 解析成 `{width, height, duration, videoCodec, audioCodec, hasAudio, avgFrameRate, nominalFrameRate, frameCount, variableFrameRate}`（对齐 `media-normalization.ts` 的 `probeVideo`）。
- 旋转流交换宽高；`qualityRisks` 规则对齐原版（low_resolution/mono_audio/very_short/variable_frame_rate/low_frame_rate）。
- `probe_media` 工具（移除 DEFERRED）降级为本地 ffprobe。

## 5. SQLite KV 持久化

- 新增 `backend/app/storage/sqlite_store.py`：
  - `kv(k TEXT PRIMARY KEY, v TEXT NOT NULL)` + `storage_migration_state(singleton, state, receipt)`。
  - `PRAGMA journal_mode=WAL`，`BEGIN IMMEDIATE` 事务。
  - `get(k)`/`put(k,v)`/`delete(k)`；`v` 是 `json.dumps` 的文档。
- 键：`project:<id>`（完整 ProjectDoc）、`generation-jobs:snapshot`（mock job store 可选落盘）、`deleted-projects:v1`。
- 迁移：`persist.py` 的 `save_project`/`load_project` 改为读写 SQLite `project:<id>`；首启从旧 `data/project.json` 导入并写 `storage_migration_state` receipt，之后用 SQLite。
- 保留 `OPENCHATCUT_DATA_DIR` 定位 DB 文件路径。
- FTS5/vec0 不做（搜索增强，延后）。

## 关键环境依赖

- `faster-whisper`（含 `ctranslate2`）
- `ffmpeg` / `ffprobe` 二进制（PATH 或 env 覆盖）

## 风险与回滚

- faster-whisper/ffmpeg 在 Windows 上的安装可能失败 → 服务层函数对「依赖缺失」返回明确错误（而非崩溃），工具返回 `{ok:false, error}`，让 agent 循环仍可跑（mock 模式不受影响）。
- SQLite 迁移失败 → 保留 JSON 回退路径，receipt 缺失时仍走 JSON。
