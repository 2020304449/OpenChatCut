# Research: 媒体探测 ffprobe

- **Query**: probe_media 如何调 ffprobe，返回哪些字段
- **Scope**: internal
- **Date**: 2026-08-28

## 结论概览

原版有**两处 ffprobe**，用途不同：

1. **Agent 工具 `probe_media`**（`src/agent/tools/probe-tools.ts`）：在 **e2b 沙箱**里跑 ffprobe（经 `/e2b/run` 代理），用于「上传 finalize 前」探测外部/本地源，产出含 `qualityRisks` 的结构化结果。
2. **服务端本地 ffprobe**（`server/media-normalization.ts` `probeVideo`）：import/normalize 流程用，直接用 `ffprobe-static` 本地探测视频元数据（更丰富，含旋转/帧数/码率/VFR 判断）。

两者都靠 `server/media-binaries.ts` 的 `ffprobeBin()` 解析二进制（`OPENCHATCUT_FFPROBE`/`FFPROBE_PATH` 覆盖 → `@ffprobe-installer/ffprobe` → `'ffprobe'`）。

## 1. probe_media 工具（e2b 沙箱）

schema（`src/agent/tools/schemas/probe-tools.ts:3-16`）：参数 `source`(required)，接受媒体池 assetId/前缀、本地 `/media/…` 路径、或公开 https URL。

executor（`probe-tools.ts:101-143`）：
- `resolveSource` 把 `source` 解析为 URL（https 直连 `direct:true`；`/media/` 或资产 src 本地路径 `direct:false`，需先拉进沙箱作 `input.media`）。
- 构造命令：`ffprobe -v quiet -print_format json -show_streams -show_format <target>`。
- `POST /e2b/run`，body `{ command, files:[{path:'input.media', url}]? }`。exitCode!==0 返回 `{ error, stderr }`。

`parseProbe`（`probe-tools.ts:38-77`）纯函数归一化，返回 `ProbeResult`：

```
{ durationSeconds?, width?, height?, fps?,
  hasAudioTrack, hasVideoTrack,
  videoCodec?, audioCodec?,
  qualityRisks: string[] }
```

字段来源：
- duration：`format.duration ?? video.duration ?? audio.duration`
- width/height：`video.width/height`
- fps：`parseFrameRate(video.avg_frame_rate)` 优先，否则 `r_frame_rate`（解析 `"30000/1001"` 这类有理数）
- videoCodec/audioCodec：`codec_name`
- `qualityRisks` 规则：`low_resolution`(w<720||h<480)、`mono_audio`(channels===1)、`very_short`(<3s)、`variable_frame_rate`(avg≠nominal 差>0.01)、`low_frame_rate`(fps<20)

最终返回（`probe-tools.ts:135-142`）：`{ ok, source, ...ProbeResult, next }`，`next` 提示后续是否 `finalize_uploaded_asset` + 是否 `transcribe_track`。

注意：e2b 沙箱不可用时 probe 会失败，但注释明确 finalize 可带 ingest 默认值继续，不阻塞。

## 2. 服务端本地 ffprobe（import/normalize）

`server/media-normalization.ts:212-262` `probeVideo(path, signal)`：命令 `ffprobe -v error -show_streams -show_format -of json <path>`，返回 `ProbeMeta`（更丰富）：

```
{ width, height, duration, videoCodec, audioCodec, hasAudio,
  sourceBitrate, size, avgFrameRate, nominalFrameRate, frameCount,
  variableFrameRate }
```

- `displayDimensions`（`:189`）处理旋转流（±90/270 交换宽高）；`rotationOf`（`:197`）读 `rotation`/`tags.rotate`/`side_data_list`。
- `variableFrameRate` = `isVariableFrameRate(avgFrameRate, nominalFrameRate)`。
- `playableDurationSeconds`（`:180`）优先 `frameCount / fps`。

还有 `server/plugins/video-media.ts:257` 一个更简的 `probeVideo`（返回 `{durationSeconds, width?, height?}`），供部分导入路径用。

## 3. export QA 里的 ffprobe

`server/plugins/export-qa.ts:111-130` `probeMedia(file)`：`ffprobe -v error -show_streams -show_format -of json <file>`，返回 `{ durationSeconds, width, height, fps, hasVideo, hasAudio }`（`parseRate` 解析 avg/r_frame_rate）。同一文件还 `analyzeVideo`（ffmpeg blackdetect/freezedetect）与 `analyzeAudio`（silencedetect/volumedetect）。

## 二进制解析（`server/media-binaries.ts`）

```ts
ffprobeBin() = env OPENCHATCUT_FFPROBE ?? FFPROBE_PATH ?? @ffprobe-installer/ffprobe.path ?? 'ffprobe'
ffmpegBin()  = env OPENCHATCUT_FFMPEG  ?? FFMPEG_PATH  ?? ffmpeg-static ?? 'ffmpeg'
```

## 事实 vs 推断

**确定的事实**：`probe_media` 工具在 e2b 沙箱跑 ffprobe（而非本地 server ffprobe），字段如上；本地 ingest 用 `media-normalization.ts` 的 `probeVideo`（字段更全）。这是两套独立探测。

**推断**：Python 后端「媒体探测 ffprobe」的对齐点应落在 **server 本地 `probeVideo`**（`media-normalization.ts`）这层——它是 import/normalize 实际依赖的探测，字段覆盖 `width/height/duration/videoCodec/audioCodec/hasAudio/avgFrameRate/nominalFrameRate/frameCount/variableFrameRate`。`probe_media` 工具的 e2b 沙箱路径是「上传 finalize 前的可选 QA」，若无 e2b 环境可降级为本地 ffprobe 等价实现。
