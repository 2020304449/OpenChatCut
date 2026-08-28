# Research: 18 个 DEFERRED 工具的原版实现

- **Query**: 18 个 DEFERRED 工具（生成类/导出类）在原版 OpenChatCut 的完整签名、行为、返回
- **Scope**: internal
- **Date**: 2026-08-28

## 结论概览

原版是「工具 = schema + 幂等包装 + executor 处理器」三层结构。schema 定义在 `src/agent/tools/schemas/*.ts` 与 `src/agent/tools/generate-schemas.ts`，executor 在 `src/agent/tools/*.ts`，调度在 `src/agent/tools.ts`（动态 import 映射，见下方「调度映射」）。全部 18 个工具在原版都**已实现**，且大多是「浏览器端 Agent 调外部付费服务 / dev-server 的 HTTP 接口」，并非纯前端本地逻辑。Python 迁移版需要对齐这些契约（尤其返回结构里的 `jobId`/`renderId`/`operationId` 约定）。

### 调度映射（`src/agent/tools.ts:229-309`）

| executor 模块 | 覆盖工具 |
|---|---|
| `generate-tools.ts` → `execGenerateTool` | submit_image / submit_voice / submit_sound / submit_music / submit_video / track_progress(generation) / rerun_generation / submit_export |
| `shader-tools.ts` → `execShaderTool` | submit_shader |
| `export-tools.ts` → `execExportTool` | submit_render_job / track_export / read_export_history |
| `export-qa-tools.ts` → `execExportQaTool` | verify_export |
| `mg-video-tools.ts` → `execMgVideoTool` | convert_motion_graphic_to_video / register_converted_video / export_motion_graphic_prores |
| `mg-code-tools.ts` → `execMgCodeTool` | create_motion_graphic_from_code |
| `probe-tools.ts` → `execProbeTool` | probe_media（非 DEFERRED，但同层） |
| `core-tools.ts` → `createMotionGraphic` | submit_motion_graphic（别名 create_motion_graphic） |
| `jianying-export-tool.ts` → `execJianyingExport` | export_jianying_draft |

注意：`submit_export` 在 schema 里归 `GENERATE_TOOL_SCHEMAS`（`generate-schemas.ts:212`），由 `generate-tool-handlers.ts` 的 `submitExportHandler` 处理（同步导出）。异步导出另立 `submit_render_job`（`schemas/export-tools.ts`），原因见 `export-tools.ts:18-25` 的注释：`submit_export` 被同步版本占用了名字。

---

## 生成类 10 个

### 1. submit_image（`schemas` 见 `generate-schemas.ts:7-33`）

- **行为**：生成 1+ 张图，写入媒体池，可选提议加入时间线。支持 gpt-image-2 / nano-banana / image-01 / wavespeed / byteplus / grok-imagine。
- **关键参数**：`model`(enum)、`prompt`(required)、`name`(required)、`addToTimeline`(bool 默认 true)、`aspectRatio`(enum)、`imageSize`(512px/1K/2K/4K)、`width/height`(int 512-3840)、`quality`、`referenceAssetIds`(array≤16)、`maskAssetId`、`count`(1-10)、`background`、`moderation`、`inputFidelity`、`outputFormat`(png/jpeg/webp)、`outputCompression`、`seed`、`promptOptimizer`。
- **返回**（`generate-tool-handlers.ts:53-63`）：`{ ok, model, generated:[{assetId,name,src,width,height}], addedTo: 'media-pool-and-proposed-timeline' | 'media-pool' }`。
- **实现层**：`submitImage` 在 `src/generate/image.ts`；幂等键 `generationIdempotencyKey` 在 `generate-tools.ts:260`。

### 2. submit_voice（`generate-schemas.ts:36-91`）

- **行为**：生成 1 个 TTS 音频资产（仅进媒体池，不放置时间线）。provider：elevenlabs/doubao/minimax/inworld/fishaudio/speechify/openai/gemini/mistral/cartesia。
- **关键参数**：`provider`(required)、`text`(required)、`voiceId`、`modelId`、`stability`、`speed`、`similarityBoost`、`style`、`useSpeakerBoost`、`languageCode`、`seed`、`outputFormat`、`instructions`、`optimizeStreamingLatency`、`enableLogging`、`applyTextNormalization`、`pronunciationDictionaryLocators`、`previousText/nextText`、`previousRequestIds/nextRequestIds`、`speedRatio/emotion/emotionScale/loudnessRatio/pitch/volume/performancePrompt/explicitDialect`(Doubao)、`sampleRate/bitrate/audioFormat/channel/forceCbr/stream/excludeAggregatedAudio/languageBoost/textNormalization/latexRead/pronunciations/timbreWeights/voiceModify/subtitleEnable/subtitleType`(MiniMax)、`name`。
- **返回**（`generate-tool-handlers.ts:65-73`）：`{ ok, provider, voiceId, assetId, name, src, subtitlePath?, addedTo:'media-pool' }`。
- **实现层**：`submitVoice` 在 `src/generate/voice.ts`。

### 3. submit_sound（`generate-schemas.ts:94-108`）

- **行为**：生成 1 个音效资产。elevenlabs 同步文字→音效；sonilo 从项目视频资产异步提交 SFX job（返回 jobId 供 track_progress）。不放置时间线。
- **参数**：`provider`(elevenlabs/sonilo)、`prompt`(elevenlabs 必需)、`durationSeconds`(0.5-30)、`promptInfluence`(0-1)、`loop`、`outputFormat`、`sourceAssetId`(sonilo 用)、`name`。
- **返回**：elevenlabs 同步 → `{ ok, assetId, name, src, durationInFrames, addedTo:'media-pool' }`（`generate-tool-handlers.ts:75-80`）；sonilo 异步 → `{ ok, ...submission, next:"Call track_progress ... jobIds=<jobId>" }`（`:99-100`）。
- **幂等/持久化**：`submit_sound`(非 sonilo) / `submit_music` / `submit_video` 是「durable generation tool」，走 `reserveGenerationOperation`（`generate-tools.ts:300-330`），需要持久化 projectId，缺省报 `generation_project_required`。

### 4. submit_music（`generate-schemas.ts:111-145`）

- **行为**：提交 Mureka / MiniMax / Atlas Cloud / Sonilo 音乐 job。mode：Mureka instrumental/song/prompt-song/soundtrack/track；MiniMax t2m/cover；Atlas t2m；Sonilo v2m。结果入媒体池。
- **参数**：`prompt`(≤2000)、`provider`(mureka/minimax/atlas/sonilo)、`mode`、`lyrics`、`isInstrumental`、`lyricsOptimizer`、`sampleRate`、`bitrate`、`audioFormat`、`referenceAssetId`/`coverFeatureId`(cover)、`count`(1-3)、`stream`、`styles`、`gender`、`referenceId`/`instrumentalId`/`vocalId`/`melodyId`/`sourceAssetId`/`audioStartMs`/`audioEndMs`/`songId`/`trackType`/`generateStartMs`/`generateEndMs`/`vocalGender`、`name`。
- **返回**：`{ ok, ...submission, next:"Call track_progress ... jobIds=<jobId>" }`（`generate-tool-handlers.ts:199-224`）。
- **实现层**：`submitMusic` 在 `src/generate/music.ts`。

### 5. submit_video（`generate-schemas.ts:148-183`）

- **行为**：提交 Seedance 2.0 / Kling / MiniMax Hailuo / BytePlus Seedance / xAI Grok Imagine 视频生成 job，建 1 个视频资产进媒体池，不放置时间线。
- **参数**：`model`(required; seedance2/kling/hailuo/byteplus/grok-imagine-video)、`prompt`、`name`、`durationSeconds`、`ratio`、`resolution`(480p/512p/720p/1080p/4k)、`mode`(std/pro)、`firstFrame`/`lastFrame`/`refImages`/`refVideos`/`refAudios`、`refVideoMode`、`promptOptimizer`、`fastPretreatment`、`generateAudio`、`seed`、`cameraFixed`、`watermark`、`returnLastFrame`、`executionExpiresAfter`、`priority`、`multiPrompts`、`shotType`。
- **返回**：`{ ok, model, ...submission, next:"Call track_progress ... jobIds=<jobId>" }`（`generate-tool-handlers.ts:226-251`）。
- **实现层**：`submitVideo` 在 `src/generate/video.ts`。

### 6. track_progress（`generate-schemas.ts:186-199` + `schemas/progress.ts` 扩展）

- **行为**：检查/等待异步生成 job（Sonilo submit_sound、submit_music、submit_video）。成功结果只入媒体池一次。经 `withProgressTargets` 扩展后 target 可为 `generation`/`transcription`/`upload`/`visual-analysis`。
- **参数**：`action`(params/status/wait/resume, required)、`target`(enum，默认 generation)、`jobIds`(逗号分隔, required)、`assetIds`(transcription/upload/visual-analysis 用)、`timeoutSeconds`(0-3600, 默认 90)。
- **返回**（`generate-tool-handlers.ts:253-271`）：`{ ok, target, action, reports, addedAssets:[{assetId,name,src,kind}], addedTo:'media-pool'? }`。
- **调度**：`progress-tools.ts` 按 target 动态 import `transcription-progress` / `track-progress-targets` / `generate-tools`。
- **实现层**：`trackGenerationProgress` 在 `src/generate/progress.ts`；job 注册在 `src/persist/jobRegistryStore.ts`。

### 7. rerun_generation（`generate-schemas.ts:201-210`）

- **行为**：用原始完整 submit 参数显式重跑一次已跟踪的生成操作。精确 operation/job ID 优先，唯一前缀可接受；歧义前缀在调 provider 前拒绝。
- **参数**：`jobId`(required)。
- **返回**（`generate-tool-handlers.ts:359-390`）：`{ ...rerunResult, rerunOf: operationId }`；失败返回 `{ error, code, candidates }` 或 `{ error, code:'legacy_summary' }`。
- **实现层**：`resolveTrackedJobForProject` 在 `src/persist/jobRegistryStore.ts`。

### 8. submit_motion_graphic（`schemas/core-tools.ts:112-135`，别名 create_motion_graphic `:137-153`）

- **行为**：同步 LLM 代码生成 + 沙箱校验，从 brief 创建 1 个 motion-graphic 资产（仅媒体池，不放置时间线）。
- **参数**：`prompt`/`description`(别名)、`name`(required)、`durationSeconds`(默认 3)、`durationInFrames`、`width`(默认 1920)、`height`(默认 1080)。
- **返回**（`core-tools.ts:102-130`）：`{ ok, status:'succeeded', jobId:'mg_<assetId>', assetId, ... }`。
- **实现**：`generateMgCode` 生成 Remotion React 组件（`core-tools.ts:75-86`），`prepareTemplate` 沙箱校验（`src/template-host.ts`）。

### 9. create_motion_graphic_from_code（`schemas/mg-code-tools.ts:3-39`）

- **行为**：从内联 React/JSX 代码注册 motion-graphic 资产（非文件路径）。必须单次传完整 JSX；不自动放置时间线。
- **参数**：`code`(required)、`name`(required)、`width`(required)、`height`(required)、`durationInFrames`/`durationInSeconds`(互斥)、`description`、`properties`([{key,label?,type?,defaultValue}])、`projectId`(忽略)。
- **返回**（`mg-code-tools.ts:75-84`）：`{ ok, assetId, name, kind:'motion-graphic', width, height, durationInFrames, note }`。
- **实现**：`prepareTemplate` 沙箱校验后 `ctx.commands.addAsset`。

### 10. submit_shader（`schemas/shader-tools.ts:3-39`）

- **行为**：自然语言→WebGL2 GLSL fragment shader→静态+浏览器编译校验→注册（不应用）。type=effect 返回 `effectId`；type=transition 返回 `transitionId`(custom:tr-*)。应用是后续独立调用。
- **参数**：`type`(effect/transition, required)、`prompt`(required)、`name`、`referenceAssetIds`(array；image 作视觉参考，effect/transition 作代码风格参考，且 kind 须匹配 type)、`properties`([{key(required),label,default,min,max,step}])。
- **返回**（`shader-tools.ts:397-422`）：effect → `{ ok, effectId, name, properties:[{key,default,min,max}] }`；transition → `{ ok, transitionId, assetId, name, properties }`。
- **实现**：`validateShaderSource`/`validateTransitionShaderSource` + `compileCheck`(WebGL2 真编译) + `registerCustomFx`/`registerCustomTransition`。

---

## 导出类 8 个

### 11. submit_export（`generate-schemas.ts:212-268`，同步导出）

- **行为**：同步导出激活时间线为 MP4/WebM 视频、MP3/WAV 音频、SRT/TXT 字幕、或 FCPXML 工程。format=xml 时 nleFormat 选 fcp_xml(Premiere)/fcp_xml_resolve(Resolve)。字体不可加载时第一次返回 `unsupportedFonts`，需 `confirmFontFallback=true` 重试。帧范围半开 `[startFrame, endFrameExclusive)`。
- **参数**：`format`(video/audio/subtitles/xml)、`codec`(h264/vp8/mp3/wav)、`subtitleFormat`(srt/txt)、`captionTrackId`、`nleFormat`、`name`、`fps`(24/25/30/50/60)、`resolution`(480p/720p/1080p)、`videoBitrate`(1e6-8e7)、`timelineId`、`startFrame`/`endFrameExclusive`/`startSeconds`/`endSeconds`、`confirmFontFallback`、`motionGraphicRenderKeys`(array)。
- **返回**：视频/音频走 `submitMediaExport`；字幕走 `submitSubtitleExport`；xml 走 `timelineToFcpxml` 并触发浏览器下载。各自 `{ ok, ...result }`（`generate-tool-handlers.ts:292-357`）。
- **实现层**：`src/generate/media-export.ts`、`src/generate/subtitles.ts`、`src/export/fcpxml.ts`。

### 12. submit_render_job（`schemas/export-tools.ts:7-29`，异步渲染）

- **行为**：异步渲染激活时间线为 MP4/WebM 视频或 MP3/WAV 音频，立即返回 `renderId`；job 出现在编辑器右上角导出队列。完成后可 `track_export` 拿 downloadUrl。
- **参数**：`format`(video/audio)、`codec`(h264/vp8/mp3/wav)、`resolution`(480p/720p/1080p)、`fps`(24/25/30/50/60)、`videoBitrate`、`name`、`startFrame`/`endFrameExclusive`/`startSeconds`/`endSeconds`、`saveToMediaPool`(bool)。
- **返回**（`export-tools.ts:241-247`）：`{ ok, renderId, format, mediaPoolStatus:'pending'?, next:"Call track_export once ... action=wait, timeoutSeconds=20 ..." }`。
- **实现**：`materializeTimelineExport` 把 project+state 快照 `POST /export/job`（dev-server），后端 `server/plugins/export-job-routes.ts` 用 `createGenerationJob` 排队渲染。

### 13. track_export（`schemas/export-tools.ts:31-45`）

- **行为**：检查渲染/导出 job。action=status 立即返回；action=wait 轮询到终态或 timeoutSeconds 到。renderIds 可逗号分隔/前缀；省略则 latest=true。返回 status/progress，完成时含 `downloadUrl` + `mediaPoolStatus`。
- **参数**：`action`(status/wait, required)、`renderIds`、`latest`、`onlyActive`、`timelineId`、`timeoutSeconds`(0-3600, 默认 20)。
- **返回**：单 job 扁平返回 `{ ok, renderId, status, progress, downloadUrl?, name?, sizeBytes?, codec?, durationSeconds?, width?, height?, fps?, sourceStartSeconds?, mediaPoolStatus?, mediaAssetId?, mediaPoolPath?, mediaPoolError?, error? }`；多 job `{ ok, count, jobs }`（`export-tools.ts:334-337`）。wait 超时加 `waitExpired:true, background:true`。
- **实现**：`fetch /export/job/:id`（`export-tools.ts:161-189`），映射 `succeeded`→`completed`。

### 14. verify_export（`schemas/export-qa-tools.ts:4-21`）

- **行为**：对已完成导出做 QA。检查流存在性、时长、分辨率、帧率、黑帧/冻结帧、长静音、音频峰值；返回结构化问题列表 + 剪辑点前后对照 contact-sheet（base64）。
- **参数**：`renderId` 或 `src`(/media/uploads/ 下)、`maxCuts`(1-8, 默认 8)。
- **返回**（`export-qa-tools.ts:95-108`）：`{ ok, src, report, cutCount, evidenceSamples, __images?[{frame,base64}], note, next }`。
- **实现**：`fetch /api/export-qa`（`server/plugins/export-qa.ts` 用 ffprobe+ffmpeg blackdetect/silencedetect+抽帧拼图）。

### 15. export_motion_graphic_prores（`schemas/mg-video-tools.ts:35-58`）

- **行为**：把 MG clip 导出为透明 ProRes 4444 .mov（保 alpha，浏览器下载）。NLE 交接格式，XML 导出前用。按 itemId(s)/assetId(s) 批量。
- **参数**：`itemId`/`itemIds`(array)/`assetId`/`assetIds`(array)、`filenameMode`(asset/xml)、`name`、`preferTimelineInstance`(默认 true)、`timelineId`。
- **返回**（`mg-video-tools.ts:354-368`）：`{ ok, timeline:{id,name}, exported:[filename 去 .mov], renders:[{itemId,assetId,renderKey,filename,usedTimelineInstance}], failed?, format:'prores4444_mov', transparent:true }`。
- **实现**：`exportClipMov` 在 `src/media/clipExport.ts`；renderKey 在 `src/export/motionGraphicRefs.ts`。

### 16. convert_motion_graphic_to_video（`schemas/mg-video-tools.ts:4-17`）

- **行为**：把时间线上的 MG（或任意非音频 clip）烘焙为媒体池真实视频资产。透明 MG/text/svg → VP9 alpha WebM（沙箱）；沙箱不可用回退不透明 h264。栅格 clip → 不透明 h264。
- **参数**：`itemId`(首选)/`assetId`、`replace`(bool，原位替换)、`opaque`(bool，强制不透明 h264)。
- **返回**（`mg-video-tools.ts:87-94`）：`{ ok, assetId, src, name, durationInFrames, replaced, transparent, codec:'vp9-alpha-webm'|'h264', note }`。
- **实现**：`bakeClipToVideo` / `bakeClipToAlphaWebm` 在 `src/media/clipExport.ts`（`/render-clip` 端点）。

### 17. register_converted_video（`schemas/mg-video-tools.ts:19-33`）

- **行为**：MG→video 流程第 2 步。track_export 报完成后，用 `renderId`（首选）把渲染产物提升为媒体池视频资产（本地后端自行解析输出，无需 downloadUrl）。重复调用去重到同一资产。
- **参数**：`mgAssetId`(required)、`renderId`(首选)/`outputUrl`(fallback)、`name`、`durationInFrames`。
- **返回**（`mg-video-tools.ts:138-154`）：`{ ok, assetId, videoAssetId, mgAssetId, name, durationInFrames, next }`；去重时加 `deduped:true`。
- **实现**：`fetchRenderJob(renderId)` 取 downloadUrl，按 src 去重后 `addAsset`。

### 18. export_jianying_draft（`jianying-export-tool.ts:7-20`）

- **行为**：把当前时间线导出为剪映/CapCut 草稿（经 capcut-cli），出现在剪映项目列表。仅在用户显式确认后调用。
- **参数**：`draftName`、`draftsDir`（additionalProperties:false）。
- **返回**（`jianying-export-tool.ts:96-105`）：`{ ok, draftName, draftPath, addedVideos, addedAudios, captions, warnings, note }`。
- **实现**：`POST /api/external-agent/jianying-export`，body 含 `fps`、`items`(kind/src/startFrame/durationInFrames/volume/name)、`captions`（由 `captionCues` 把词级 transcript 合并成短语 cue，gap≤450ms 归并，`jianying-export-tool.ts:28-64`）。

---

## 关键事实 vs 推断

**确定的事实**：以上所有 18 个工具的 schema 与 executor 均存在于上述文件，返回结构已逐一核对代码。

**推断**：
- 「18 个 DEFERRED 工具」对应的原版实现**全部是浏览器端 Agent 工具**，最终落点是外部付费服务 API 或 dev-server HTTP 端点（`/export/job`、`/api/export-qa`、`/api/external-agent/jianying-export`、`/e2b/run` 等）。Python FastAPI 后端补齐这些能力时，生成类工具需要对接**外部 provider**（DALL-E/MiniMax/ElevenLabs/Sonilo 等），导出类需要对接 **Remotion/FFmpeg 渲染**（见 export-ffmpeg.md），并非纯命令即可完成。
- `submit_image`/`submit_voice`/`submit_sound`(elevenlabs) 是同步返回资产；`submit_sound`(sonilo)/`submit_music`/`submit_video` 是异步 job（配 `track_progress`/`rerun_generation`）。这条「同步 vs 异步」分界线是幂等与持久化的核心差异。

## Related Specs / 相关文件索引

- 后端 DEFERRED 标记：`learning/openchatcut-backend/backend/app/agent/tools.py:33-44`
- 后端工具清单：`learning/openchatcut-backend/backend/app/agent/tools.py:878-926`（TOOLS 列表）
- 原版工具注册：`src/agent/tools.ts`
- 生成类 schema：`src/agent/tools/generate-schemas.ts`
- 生成类幂等：`src/agent/tools/generate-tools.ts`
