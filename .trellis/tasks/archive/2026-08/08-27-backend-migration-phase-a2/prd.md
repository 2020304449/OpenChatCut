# 后端迁移 A-2: 补全编辑命令(文本稿+片段属性+项目级)

## Goal

在 A-1 的基础上，补全 OpenChatCut 剩余约 35 种**编辑命令**（不是生成/导出），把编辑核心覆盖到 78 种 Action 的完整核心能力。重点是**文本稿词级编辑**——这是 OpenChatCut「文字稿驱动」的核心差异化。

## Requirements

### R1 — 数据模型扩展（transcript 词级）
- 新增 `TranscriptWord`：`id/text/startMs/endMs/speaker`（**毫秒单位**，对齐源码 `src/transcript/types.ts`）。
- 新增 `TranscriptVariant` + `TranscriptVariantWord`（翻译/修正变体，sparse overlay，按源词索引 `i` 覆盖）。
- `TimelineItem` 扩展 transcript 字段：`transcript`、`transcriptGenerationId`、`transcriptStale`、`variants`、`deletedWordIdx`、`silenceFrames`、`cutPadFrames`、`gapCapsMs`、`transcriptPlayOrder`。
- **关键决策**：transcript 时间戳用 ms，clip 用帧；提供 `ms_to_frame(ms, fps)` 转换（对齐源码 `msToFrame`）。

### R2 — 文本稿词级命令（12 种）
`setItemTranscript` / `setItemVariants` / `toggleWord` / `deleteWords` / `cleanScript` / `setGapCap` / `setTranscriptPlayOrder` / `reorderTrackItems` / `clearEdits` / `fixTranscriptWord` / `renameSpeaker` / `pool.setTranscription`。

其中 `cleanScript`（填充词移除 + 停顿压缩）和 `reorderTrackItems`（gap-aware 原子重排）是有真实算法的命令。

### R3 — 剩余片段属性命令（8 种）
`slip` / `setBackgroundFill` / `replaceMedia` / `relinkTimelineItem` / `updateWatermark` / `setItemDenoise` / `setReframeKeyframe` / `removeReframeKeyframe`。

### R4 — 项目级命令（约 15 种）
- `tl.*` 完整：`tl.create` / `tl.switch` / `tl.duplicate` / `tl.delete` / `tl.rename` / `tl.retarget` / `tl.setHidden` / `tl.setDoc`
- `pool.*` 剩余：`pool.renameFolder` / `pool.deleteFolder` / `pool.updateAsset` / `pool.relinkAsset` / `pool.canonicalizeAsset`
- `design.set` / `design.patch`
- `setFullState`

### R5 — 工具面
- 对应 R2/R3/R4 命令的工具（约 15~20 个），沿用 A-1 的细粒度「一命令一工具」风格。
- 文本稿工具对齐 OpenChatCut 命名：`transcribe_track` / `clean_script` / `delete_text` / `manage_transcript` / `read_transcript` / `read_script` 等。

### R6 — 延后项标记
- 生成类（submit_image/voice/music/video 等）与导出类（submit_export 等）工具，在代码与文档中用统一标记 `[DEFERRED]` 记录，注明依赖（外部服务/渲染引擎），方便后续 grep 补充。

## Acceptance Criteria

- [ ] 数据模型能表达「词级转写 + 翻译变体 + 删词索引 + 停顿压缩」，`to_dict` 往返序列化无损（含 ms 时间戳）。
- [ ] R2/R3/R4 的 35 种命令每种有 apply 实现 + 至少一条 pytest 断言。
- [ ] `cleanScript` 正确：移除填充词、按 `silenceFrames` 压缩词间停顿、产出新的词级时间轴。
- [ ] `ms_to_frame` 转换正确（30fps 下 1000ms = 30 帧）。
- [ ] 工具面覆盖全部新增命令，`GET /api/tools` 返回对应 schema。
- [ ] mock/真实 LLM 下，一句含「删掉口误和停顿」的指令能触发 `clean_script` 类工具。
- [ ] 生成/导出延后项在代码中有 `[DEFERRED]` 标记可 grep。

## Out of Scope

- **[DEFERRED] 生成类工具**：submit_image / submit_voice / submit_sound / submit_music / submit_video / submit_motion_graphic / create_motion_graphic_from_code / submit_shader / track_progress / rerun_generation —— 依赖外部付费服务（DALL-E/TTS/音乐 API/视频生成）。
- **[DEFERRED] 导出类工具**：submit_export / submit_render_job / track_export / verify_export / export_motion_graphic_prores / register_converted_video / convert_motion_graphic_to_video / export_jianying_draft —— 依赖渲染引擎（Remotion/FFmpeg），属阶段 C/D。
- **[DEFERRED] 高级智能**：multicam（多机位）/ linkGroups（链接组）/ 音乐节奏剪辑 / 自动调色 / 场景检测 / 高光提取 / reframe 自动 / 人脸避让 —— 依赖重计算或外部模型。
- MCP、前端、渲染、持久化（同 A-1）。

## Key Decisions

- **transcript 用 ms、clip 用帧**：对齐源码，`ms_to_frame` 在两者间转换。
- 命令作用域沿用 A-1：时间线命令落 `activeTimeline`，项目级命令落 `ProjectDoc` 顶层。
- 撤销单位沿用快照撤销（一命令一节点）。
- 延后项用统一 `[DEFERRED]` 标记，集中记录在 design.md 的「延后项追踪」表 + 代码注释。
