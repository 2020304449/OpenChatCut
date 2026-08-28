# Research: 导出 FFmpeg / Remotion

- **Query**: submit_export / render 怎么实现，输入（时间线数据）和输出（MP4/SRT），渲染引擎是 Remotion 还是 FFmpeg 还是两者
- **Scope**: internal
- **Date**: 2026-08-28

## 结论概览

**两者都用，且分层明确**：渲染引擎是 **Remotion**（`@remotion/renderer` 4.0.509），FFmpeg 是 Remotion 底层的编码/复用器（`@remotion/renderer` 自带 FFmpeg 二进制，`remotionFfmpegPath()`）。此外还有两条纯 FFmpeg 的辅助路径：浏览器端 **WebCodecs 快导**（`@remotion/web-renderer`，不经过 server FFmpeg）和 **FPS 重定时（retimeFps）** 的二次编码。

三条渲染路径：
1. **server 端 Remotion 渲染**（异步 `submit_render_job` / 同步 `submit_export`）→ `remotion/render.mjs` `renderTimeline`。
2. **浏览器端 WebCodecs 快导** → `@remotion/web-renderer` `renderMediaOnWeb`（`src/export/browserExport.ts`），失败回退 server。
3. **单 clip 烘焙**（MG→video / ProRes）→ `renderClip`（透明 ProRes 4444 / VP9 alpha webm）。

## 依赖

`package.json`：
- `@remotion/bundler` `4.0.509`、`@remotion/renderer` `4.0.509`、`@remotion/web-renderer` `4.0.509`、`remotion` `4.0.509`、`@remotion/player`、`@remotion/media`、`@remotion/google-fonts`
- `ffmpeg-static` `^5.3.0`、`@ffprobe-installer/ffprobe` `^2.1.2`

## server 端渲染管线（`remotion/render.mjs`）

`renderTimeline({state, project, timelineId, outputLocation, codec, frameRange, scale, videoBitrate, h264Profile, vaapiDevice, signal})`：
1. `getServeUrl()` → `@remotion/bundler` `bundle()` 把 `remotion/index.ts` 打包成 serve bundle（webpack），`publicDir=assets/`，`.frag` 经 `type:'asset/source'` 作 raw 文本（`render.mjs:187-216`）。
2. 把 `<serveUrl>/media/uploads` symlink（win32 用 junction）到实时上传目录，使运行时新增媒体立即可渲染（`relinkUploads` `:225-238`）。
3. `selectComposition`（headless Chrome）+ `renderMedia`，codec 支持 `h264|vp8|prores|mp3|wav`。ProRes 全时间线母带用 `proResProfile:'hq', imageFormat:'png'`（`render.mjs:307-309`）；单 clip 透明用 `proResProfile:'4444', pixelFormat:'yuva444p10le'`（`render.mjs:400-402`）。
4. 硬件加速：`remotionHardwareAcceleration` / `h264FfmpegOverride` / `direct-hardware.mjs`（`renderMediaOptimized` `:118-165`），失败自动回退软件编码。

`Root.tsx`：单个 `Composition`（id=`timeline`）渲染整个编辑器时间线，`component=TimelineComposition`，`calculateMetadata` 从 `state` 输入 props 推导 duration/fps/宽高（`remotion/Root.tsx`）。

`renderTimelineStills`：`renderStill` 输出 JPEG（供 `view_timeline_frames` / `view_asset_frames` 视觉工具），最多 16 帧。

`remotionFfmpegPath()`：`RenderInternals.getExecutablePath({type:'ffmpeg',...})`（`render.mjs:59-66`）——即 Remotion 内置 FFmpeg。

## server 导出端点

`server/plugins/export-job-routes.ts`：
- `POST /export/job` → `acceptExportSubmission`（校验/mater­ialize 媒体）→ `createGenerationJob` 排队 → 立即返回 `{ renderId: jobId }`（`:197-202`）。job 执行 `renderExportPlan`（`export-rendering.ts:55`），产出写入 `/media/uploads/<uuid>.<ext>`，result 含 `{ assetId, kind, name, path, durationSeconds, sizeBytes, codec, width, height, fps, sourceStartSeconds }`。
- `GET /export/job/:id` → job 快照 `{ id, status, progress, result?, error? }`。
- `DELETE /export/job/:id` → 取消/删除。
- `POST /export/job/:id/promote` → 把完成产物提升进媒体池。
- 另有同步 `POST /export`（`registerExportRoute` `:216`）直接 `renderTimeline` 后把文件流回（`Content-Disposition` 下载）。

`export-rendering.ts`：`renderExportPlan` 调 `renderTimeline`，若 `plan.retimeFps` 存在则 `retimeFps`（`export-runtime.ts`）用 FFmpeg 二次重定时后 rename。

## 浏览器快导（WebCodecs）

`src/export/browserExport.ts`：`renderTimelineInBrowser` → `@remotion/web-renderer` `renderMediaOnWeb`，`container='mp4'|'webm'`，`videoCodec='h264'|'vp8'`，`audioCodec='aac'|'opus'`，`hardwareAcceleration:'prefer-hardware'`，`getBlob()` 返回 Blob。`staticBrowserBlocker` 拒绝：codec=prores、请求 fps≠时间线 fps（`:124-143`）。`exportVideoWithFallback`：浏览器失败自动回退 server。

## 输出格式对照

| format | 输出 | 引擎 |
|---|---|---|
| video + h264 | `.mp4` (AAC) | Remotion renderMedia（server）或 web-renderer（browser） |
| video + vp8 | `.webm` (Opus) | 同上 |
| audio + mp3/wav | `.mp3`/`.wav` | Remotion renderMedia |
| subtitles (srt/txt) | 字幕文件 | `src/generate/subtitles.ts`（非渲染，纯文本导出） |
| xml (fcp_xml/fcp_xml_resolve) | `.fcpxml` | `src/export/fcpxml.ts`（纯文本工程导出，非渲染） |
| prores（MG/母带） | `.mov` ProRes 422 HQ / 4444 alpha | Remotion renderMedia（server） |
| vp9 alpha webm（MG 烘焙） | `.webm` 透明 | `renderClip` + e2b 转码 |

## 输入（时间线数据）

渲染输入是 `TimelineState`（`src/editor/types.ts`）+ 可选 `ProjectDoc` + `timelineId`，作为 Remotion `inputProps`。`materializeTimelineExport`（`src/export/materializeBlobMedia.ts`）在导出前把 blob 媒体落地；`exportMediaPlan.ts` / `server/plugins/export-media-plan.ts` 负责 media reference 物化。

## 关键事实 vs 推断

**确定的事实**：Remotion 是唯一渲染引擎；FFmpeg 作为 Remotion 的编码后端 + 独立的 FPS 重定时/媒体探测/QA 工具存在。浏览器 WebCodecs 是快导路径。字幕和 XML 导出不走渲染引擎。

**推断**：Python 后端补齐「导出 FFmpeg」能力时，若要 1:1 对齐渲染质量，最直接的路线是 shell 出 **Remotion**（Node）或等价把时间线转成渲染脚本；纯 FFmpeg 只能做到「线性拼接/滤镜」，无法复刻 motion-graphic（React/JSX）、WebGL effect/GLSL transition 等 Remotion 动态渲染。因此「导出」能力的对齐成本主要在 Remotion 渲染，而非 FFmpeg 本身。
