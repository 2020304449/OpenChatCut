# Research: 转写 ASR（whisper / transcribe_track）

- **Query**: transcribe_track 及相关工具如何调 whisper（public/whisper-cli? asr-models?），产出什么结构（词级 TranscriptWord？毫秒时间戳？），模型怎么加载
- **Scope**: internal
- **Date**: 2026-08-28

## 结论概览

原版 ASR 有**两条引擎路径**，都在客户端（browser/desktop）执行，而非 server 端：

1. **浏览器端 whisper（transformers.js）**：`@huggingface/transformers`（v3.8.1）在 WebWorker 里跑 ONNX whisper，WebGPU（Metal/D3D12/Vulkan）或 wasm 回退。词级时间戳用 `return_timestamps:'word'`，并经 `whisper-word-timestamps.ts` 打补丁修复前缀对齐。
2. **桌面原生 whisper.cpp**：桌面版（Electron）经 `window.openChatCutDesktop.inference` 桥接，调 `public/whisper-cli/win32-x64/whisper-cli.exe`（ggml whisper，另有 parakeet）。模型是 GGML 文件（如 `ggml-base-q5_1.bin`）。

无论哪条路径，最终都归一化到 **`TranscriptResult`**（词级 `TranscriptWord[]`，毫秒时间戳）。

## 数据结构（毫秒时间戳）

`src/transcript/types.ts:1-39`：

```ts
interface TranscriptWord {
  id?: string;          // 一次转写内的持久身份
  text: string;
  start: number;        // ms
  end: number;          // ms
  speaker?: string|null; // 'A'|'B'… diarization 开启时
}
interface TranscriptResult { text: string; words: TranscriptWord[]; utterances: TranscriptUtterance[]; }
interface TranscriptUtterance { speaker: string; text: string; start: number; end: number; words: TranscriptWord[]; }
```

注意：**所有时间戳是毫秒**（`start`/`end` ms），`msToFrame(ms,fps)` 转换到帧（`types.ts:86`）。后端 `TranscriptWord(startMs,endMs)` 与此对齐（见 `learning/openchatcut-backend/backend/app/domain/transcript.py`）。

浏览器 worker 输出是**秒**，在 `local-asr.worker.ts:95-109` 的 `toChunks` 里 `Math.round(start*1000)` 转毫秒；`local-asr.ts:209-221` 的 `toTranscriptResult` 再包成 `TranscriptResult`（speaker 置 null，单 utterance speaker='A'）。

## transcribe_track 工具

schema 在 `src/agent/tools/schemas/transcript-tools.ts:20-25`：参数 `track`(默认 A1)、`provider`(enum assemblyai/local/openai/mistral/deepgram/groq/elevenlabs/cartesia，省略用设置默认)。

executor 在 `src/agent/tools/transcript-tools.ts:259-299`：
- 过滤轨道上所有 audio/video clip（`it.kind==='audio'||'video'` 且有 src），按 startFrame 排序。
- 已有有效 transcript 的 clip 跳过（`hasOperationalTranscript`）。
- 每个 clip 调 `transcribePath(it.src, onProgress, {}, provider)`，结果 `ctx.commands.setItemTranscript(it.id, r.words)`。
- `TranscriptionError` code==='no-audio' 视为「跳过」而非失败。
- 返回 `{ ok, track, provider, clips, results:[{itemId,words,text,skipped?,skippedReason?}] }`；provider==='local' 失败时追加中文 guidance「检查 whisper 模型是否已下载」。

## provider 路由

`src/transcript/provider.ts:104-133`：`transcribePath` → `transcribePathResumable`，按 provider 分流：
- `local` → `localTranscribePathResumable`（`local-asr.ts`）
- `assemblyai` → `assemblyaiTranscribePathResumable`（`assemblyai.ts`，云端，凭据在 server 端）
- 其它 → `genericCloudTranscribePath`（`generic-cloud-asr.ts`）

默认 provider 是 `assemblyai`（`provider.ts:55-63`），语言默认 `zh`，diarization 默认 true。

## 浏览器端模型加载（transformers.js）

`src/transcript/local-asr.worker.ts`：
- 模型**只通过同源代理 `/api/hf-proxy`** 加载（`local-asr-model-source.ts:1-7` → `origin + '/api/hf-proxy'`），server 端 `server/plugins/hf-proxy.ts` 强约束「pinned model/revision/file 三元组 + 尺寸 + SHA-256」后才供字节。
- `env.useBrowserCache = false`（`local-asr.worker.ts:37`，绕过浏览器 Cache Storage，避免大模型文件损坏）。
- dtype：wasm 用 `q8`；webgpu 用混合 dtype `{encoder_model:'fp32', decoder_model_merged:'fp16'}`（`ASR_INFERENCE_CONTRACT.webgpuDtype`）。
- `return_timestamps:'word'`、`chunk_length_s`=30、`stride_length_s`=5（`ASR_INFERENCE_CONTRACT`）。
- 加载后 `patchWhisperWordTimestampModel`（`whisper-word-timestamps.ts:140`）打前缀对齐补丁。

`src/transcript/deviceProfile.ts:60-84`：`chooseAsrConfig` 选 tier（用户 localStorage `cc.asrModel` 覆盖，默认 `base`）与 device（`cc.asrBackend==='webgpu'` 且 tier!=='medium' 且 profile.webgpu.available 且未被标记 broken → webgpu，否则 wasm）。

`shared/asr-inference-contract.ts`：`{ id:'whisper-q8-16khz-word-v1', sampleRate:16000, maxAudioSeconds:3600, chunkSeconds:30, strideSeconds:5, dtype:'q8', webgpuDtype:{encoder_model:'fp32',decoder_model_merged:'fp16'} }`。

## 模型目录（`shared/asr-models.ts`）

4 档：tiny/base/small/medium，每档含 ONNX 文件清单（`files[].{path,sizeBytes,sha256}`）+ 可选 GGML 文件（`ggmlFile.{fileName,sizeBytes,sha256,revision}`）：
- tiny: `Xenova/whisper-tiny`（ggml-tiny-q5_1.bin）
- base: `onnx-community/whisper-base_timestamped`（ggml-base-q5_1.bin）—— 这是 word 级时间戳推荐的轻量档
- small: `Xenova/whisper-small`
- medium: `Xenova/whisper-medium`

关键注释（`asr-models.ts:1-10`）：word 级时间戳要求 ONNX 图输出 cross-attentions；旧 onnx-community 导出（无 `_timestamped` 后缀）会抛 "Model outputs must contain cross attentions"，所以 small/medium 保持 Xenova 导出，base 用 `_timestamped` 重导出。

## 模型下载/缓存（server 端）

`server/plugins/asr-models.ts`：
- `GET /api/asr-models` → catalog + 每模型 `downloaded` 状态（sha 校验）。
- `POST /api/asr-models/download` → `{ id }` 后台下载。
- `GET /api/asr-models/download/:id` → 任务状态。
- `POST /api/asr-models/delete` → 删缓存。
- 下载复用 `hf-proxy` 多源通道，缓存目录 `modelCacheDir()` = `<root>/.openchatcut/asr-models`（`hf-proxy.ts`）。

`local-asr.ts:241-259` `assertAsrModelDownloaded`：转写前先查 `/api/asr-models`，若 `downloaded===false` 抛「本地转写模型未完整下载」。

## 桌面原生 whisper.cpp

`src/transcript/desktop-native-asr.ts`：`tryDesktopNativeAsr` 通过 `window.openChatCutDesktop.inference.transcribe({requestId, contractId, sourcePath, modelId, revision, language})` 调桌面原生推理；要求 `contractId === ASR_INFERENCE_CONTRACT.id` 且 `capabilities.asr.available`。

`server/media-binaries.ts:34-49` `whisperCliBin()`：解析 `OPENCHATCUT_WHISPER_CLI` 覆盖，否则找 `public/whisper-cli/<platform>/whisper-cli.exe`（或打包 `resourcesPath/dist/...`）。`public/whisper-cli/win32-x64/` 内是 ggml whisper + parakeet 可执行文件（whisper-cli.exe、parakeet-cli.exe、ggml*.dll 等）。

## 音频提取（前置步骤）

`server/plugins/extract-audio.ts`：`POST /api/extract-audio` 从本地媒体抽低码率音频轨。浏览器 `local-asr.ts:178-207` `decodeSourceToSamples`：fetch 同源路径 → WebAudio `decodeAudioData` → `downsampleMono` 到 16kHz Float32（`client-asr-extract.ts`）。

## Related Files

- `src/transcript/types.ts`、`provider.ts`、`local-asr.ts`、`local-asr.worker.ts`、`whisper-word-timestamps.ts`、`deviceProfile.ts`、`desktop-native-asr.ts`、`assemblyai.ts`、`generic-cloud-asr.ts`
- `shared/asr-models.ts`、`shared/asr-inference-contract.ts`
- `server/plugins/asr-models.ts`、`server/plugins/hf-proxy.ts`、`server/plugins/extract-audio.ts`、`server/media-binaries.ts`
- `src/agent/tools/transcript-tools.ts`、`src/agent/tools/schemas/transcript-tools.ts`

## 事实 vs 推断

**确定的事实**：所有文件路径、毫秒时间戳结构、模型清单、加载流程均从代码直接读取。

**推断**：Python 后端若要做「真实转写 ASR」，原版引擎在浏览器/桌面，**不在 server**；server 只负责「模型下载代理（hf-proxy/asr-models）+ 音频提取（extract-audio）+ 云端 provider 凭据转发（assemblyai 等）」。后端对齐最可能落点是：把 `transcribe_track` 命令改为**调用后端一个转写服务**（接 whisper.cpp/whisper 或云端 provider），产出结构对齐 `TranscriptWord{text,startMs,endMs,speaker?}` 毫秒时间戳，然后走 `SetItemTranscript` 命令写回片段。
