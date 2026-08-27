# Research: 工具面清单（Agent Tool Surface）

- **Query**: 扫描 `src/agent/tools/` 下所有非 `.verify.ts` 工具文件，提取工具名、用途、对应 Action、参数 schema 关键字段，并按能力分组
- **Scope**: internal（代码库内部）
- **Date**: 2026-08-27

## 结论摘要

- 工具面的**权威清单**不是逐个 `.ts` 文件，而是 `src/agent/tools.ts` 的 `TOOL_SCHEMAS` 数组（编译期聚合），其编译产物是 `assets/agent/openchatcut-tool-schemas.json`（version 1，`edit` 目录 **120 个**工具、`ask` 目录 **22 个**工具）。
- `src/agent/tools/` 目录下共有 **97 个非 verify 的 `.ts` 文件**，其中 `schemas/` 子目录 54 个文件承载 schema 定义，其余是 executor 逻辑文件。
- 工具 = 命令（`tools.ts` 顶部注释原文 "Each one executes against the EditorCore command layer (tool == command)"）。每个工具最终落到 `EditorCommands`（`src/editor/storeCommands.ts`，约 90 个方法），`EditorCommands` 再 1:1 dispatch 到 `reducerActions.ts` 的 Action。
- 工具 → Action 的映射表见下方「Command/Action 映射总表」。核心数据工具（`read_timeline`/`update_item_props`/`move_item`/`set_item_timing`/`duplicate_item`/`remove_item`/`split_item`/`clear_timeline`/`set_aspect_ratio`）在 `core-data-tools.ts` 内直接调用 `ctx.commands.*`。

## 数据来源

| 文件 | 作用 |
|---|---|
| `src/agent/tools.ts` | 工具 schema 聚合 + executor 分发注册表 |
| `assets/agent/openchatcut-tool-schemas.json` | 生成的工具目录（edit 120 / ask 22） |
| `src/agent/tools/schemas/*.ts` | 每个能力域的 schema + `*_TOOL_NAMES` |
| `src/agent/tools/*.ts`（非 schemas） | executor：把工具参数翻译成 `ctx.commands.*` 调用 |
| `src/agent/execution-policy.ts` | 每个工具的 effect 分类（read / reversible_edit / persistent_local / irreversible_external） |
| `src/agent/tools/execution-modes.ts` | 并行 vs 独占执行分类 |
| `src/editor/storeCommands.ts` | `EditorCommands` 接口定义 |
| `src/editor/storeCommandBuilder.ts` | `EditorCommands` 方法 → Action 的 1:1 dispatch 实现 |
| `src/editor/reducerActions.ts` | Action 联合类型（78 种命令 Action + 项目级 Action） |

## Command/Action 映射总表（工具层 → reducerActions）

`EditorCommands` 方法名即工具底层调用的命令，右侧是对应 `reducerActions.ts` 的 Action type。

| EditorCommands 方法 | Action type |
|---|---|
| addMotionGraphic / addAudio / addMediaItem / addSolidItem / addTextClip / addSequence | `add` |
| addAsset | `addAsset` |
| updateItemProps | `updateProps` |
| moveItem | `move` |
| setItemTiming | `retime` |
| slipItem | `slip` |
| setItemVolume | `setVolume` |
| setItemFade | `setFade` |
| setItemTransform | `setTransform` |
| setItemFilters | `setFilters` |
| setItemBackgroundFill | `setBackgroundFill` |
| setItemZoom | `setZoom` |
| setItemEffects | `setEffects` |
| setItemSpeed | `setSpeed` |
| replaceItemMedia | `replaceMedia` |
| relinkTimelineItem | `relinkTimelineItem` |
| addMarker / updateMarker / removeMarker | `addMarker` / `updateMarker` / `removeMarker` |
| setReframeKeyframe / removeReframeKeyframe | `reframeKeyframe` / `removeReframeKeyframe` |
| setItemKeyframe / removeItemKeyframe / clearItemKeyframes | `setKeyframe` / `removeKeyframe` / `clearKeyframes` |
| addTransition / setTransition / removeTransition | `addTransition` / `setTransition` / `removeTransition` |
| duplicateItem | `duplicate` |
| removeItem | `remove` |
| rippleDeleteItem | `remove`（ripple:true） |
| splitItem | `split` |
| clearTimeline | `clear` |
| setAspect | `setCanvas` |
| toggleTrackFlag | `toggleTrack` |
| createTrack / updateTrack / deleteTracks / tightenTrack | `track.create` / `track.update` / `track.delete` / `track.tighten` |
| createCaptionTrack | `track.create` + `setCaptions`（batch） |
| setCaptions / updateCaptions / setCaptionsHidden | `setCaptions` / `updateCaptions` / `setCaptionsHidden` |
| updateWatermark | `updateWatermark` |
| setItemTranscript | `setItemTranscript` |
| setAssetTranscription | `pool.setTranscription` |
| setItemVariants | `setItemVariants` |
| toggleWord / deleteWords | `toggleWord` / `deleteWords` |
| cleanScript | `cleanScript` |
| setGapCap | `setGapCap` |
| setTranscriptPlayOrder | `setTranscriptPlayOrder` |
| reorderTrackItems | `reorderTrackItems` |
| clearEdits | `clearEdits` |
| fixTranscriptWord | `fixTranscriptWord` |
| renameSpeaker | `renameSpeaker` |
| setItemDenoise | `setItemDenoise` |
| selectItem / selectItems / selectAll | `select` / `selectMany` / `selectAll` |
| applyState | `setFullState` |
| applyDoc | `tl.setDoc` |
| batch | `batch` |
| createTimeline / switchTimeline / duplicateTimeline / deleteTimeline / renameTimeline / retargetTimeline / setTimelineHidden | `tl.create` / `tl.switch` / `tl.duplicate` / `tl.delete` / `tl.rename` / `tl.retarget` / `tl.setHidden` |
| createMediaFolder / renameMediaFolder / deleteMediaFolder | `pool.createFolder` / `pool.renameFolder` / `pool.deleteFolder` |
| moveMediaAssets | `pool.moveAssets` |
| renameMediaAsset / renameMediaAssets / setMediaAssetFavorite / setMediaAssetsFavorite / editMediaAsset | `pool.updateAsset`（部分 batch） |
| removeMediaAsset / removeMediaAssets | `pool.removeAsset` |
| canonicalizeMediaAsset | `pool.canonicalizeAsset` |
| relinkMediaAsset | `pool.relinkAsset` |
| setDesignStyle / patchDesignStyle | `design.set` / `design.patch` |
| undo / redo | `undo` / `redo`（HistoryControlAction） |

## 工具面分组清单

共 120 个 edit 工具，按能力分 11 组。每组列：工具名 — 一句话用途 — 对应 Action（编辑类工具）/ 读类标记。

### 1. 轨道 / 时间线管理（9 个）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| `read_timeline` | 读当前时间线 fps + 每 clip 的源链接/源窗口/可编辑状态 | 只读（纯读） |
| `edit_track` | 轨道 CRUD（list/create/update/delete/tighten/reorder_items） | `track.create`/`track.update`/`track.delete`/`track.tighten`/`reorderTrackItems` |
| `manage_timelines` | 多时间线（list/create/duplicate/switch/update/delete + 嵌套序列实例） | `tl.*` + `add`（嵌套） |
| `set_aspect_ratio` | 重定画布比例（16:9→9:16 长转短） | `setCanvas` |
| `clear_timeline` | 清空全部 clip | `clear` |
| `import_timeline` | 导入 FCPXML/EDL 为新时间线 | 项目级重建（读入+生成） |
| `multicam_sync` | 多机位持久对齐（时间码/时钟/音频相关性） | 批次（undoable） |
| `change_cam` | 多机位区间切机 | `split`/`remove` 规划 + 决策 |
| `manage_link_group` | 联动/同步锁分组（A/V 同动、定时锁） | 批次 undoable |

### 2. 片段编辑（13 个）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| `edit_item` | 统一片段级操作（adds/updates/deletes，覆盖 video/image/audio/gif/svg/MG/text/solid/effect/transition） | 复合：`add`/`updateProps`/`move`/`retime`/`slip`/`setVolume`/`setFade`/`setTransform`/`setFilters`/`setBackgroundFill`/`setZoom`/`setEffects`/`setSpeed`/`setKeyframe`/`clearKeyframes`/`addTransition`/`setTransition`/`removeTransition`/`replaceMedia`/`relinkTimelineItem`/`remove`/`applyDoc` |
| `add_motion_graphic` | 按模板名添加 MG clip（ripple 插入） | `add` |
| `add_audio` | 添加音乐/SFX 到 A1/A2 | `add`（+`addAsset` 若新资产） |
| `update_item_props` | 改 clip 可编辑 props（text/colors） | `updateProps` |
| `move_item` | 移动 clip 到轨道/帧 | `move` |
| `set_item_timing` | 重定时 + 淡入淡出 | `retime` + `setFade` |
| `duplicate_item` | 复制 clip | `duplicate` |
| `remove_item` | 删除 clip（ripple 关闭空隙） | `remove` |
| `split_item` | 在绝对帧分割 clip | `split` |
| `manage_effects` | WebGL 效果快捷（list/add/update/remove，含 LUT） | `setEffects` |
| `edit_gap` | 列出/删除词间呼吸间隙 | `setGapCap` |
| `remove_silence` | 去除死空气（相对电平检测 + 分割/删除 ripple） | `split`/`remove` 批次 |
| `apply_layout` | 多画面布局（分屏/PiP/网格）一次 undoable | `setTransform`/`setZoom`/`setCanvas` 批次 |

### 3. 转场（无独立专有工具，经由 edit_item / shader）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| （`edit_item` adds type=transition） | 添加/更新/删除转场 | `addTransition`/`setTransition`/`removeTransition` |
| `submit_shader`（type=transition） | 生成自定义 WebGL 转场 shader（双输入） | 生成资产，应用时 `addTransition` |

### 4. 字幕（4 个）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| `read_captions` | 读字幕轨道状态 + 已解析页面 | 只读 |
| `edit_captions` | 字幕管理（enable/disable/hide/show/preset/text/style…） | `setCaptions`/`updateCaptions`/`setCaptionsHidden` |
| `apply_caption_avoidance` | 字幕避让人脸（视觉几何） | `updateCaptions`（写放置策略） |
| `update_watermark` | 文字水印开关/文本/位置/不透明度 | `updateWatermark` |

### 5. 关键帧（无专有 CRUD 工具，经由 edit_item + reframe）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| （`edit_item` updates keyframes） | 通用变换关键帧 | `setKeyframe`/`removeKeyframe`/`clearKeyframes` |
| `auto_reframe` | 自动重构：采样帧检测主体 → 写 reframe 关键帧 | `setReframeKeyframe`（+`clearKeyframes`） |

### 6. 标记（2 个）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| `manage_markers` | 时间线标注/TODO 锚点（list/create/update/delete，点或范围） | `addMarker`/`updateMarker`/`removeMarker` |
| `detect_scenes`（apply=markers） | 场景检测生成 item 级标记 | `addMarker` |

### 7. 文本稿 / 转录（10 个）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| `read_transcript` | 读转录短语视图 | 只读 |
| `transcribe_track` | 轨道转录（AssemblyAI 等，附加词/说话人） | `setItemTranscript`/`setAssetTranscription` |
| `find_transcript` | 定位短语时间坐标 | 只读 |
| `clean_script` | 机械清理（填充词移除 + 停顿规则） | `cleanScript` |
| `delete_text` | 删短语（delete text = delete video） | `deleteWords` + 重定时 |
| `manage_transcript` | 源转录修正 + 翻译变体管理 | `fixTranscriptWord`/`setItemVariants`/`renameSpeaker` |
| `read_script` | 物化时间线为 timeline.md | 只读 |
| `apply_script` | 提交编辑后的 timeline.md 回时间线 | `reorderTrackItems`（+`deleteWords`）批次 |
| `search_media` | 媒体语义搜索（ChineseCLIP + 转录） | 只读 |
| `edit_project`（speaker-update） | 项目级说话人重命名/合并 | `renameSpeaker` |

### 8. 生成（13 个）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| `submit_image` | AI 图像生成（多 provider）入池 | `addAsset`（媒体池） |
| `submit_voice` | TTS 语音生成（多 provider）入池 | `addAsset` |
| `submit_sound` | SFX 生成入池 | `addAsset` |
| `submit_music` | 音乐生成（Mureka/MiniMax/Atlas/Sonilo） | `addAsset` |
| `submit_video` | 视频生成（Seedance/Kling/Hailuo…） | `addAsset` |
| `submit_motion_graphic` / `create_motion_graphic` | MG 生成（alias） | `addAsset` |
| `create_motion_graphic_from_code` | 内联 JSX → MG 资产 | `addAsset` |
| `submit_shader` | 生成 WebGL shader（effect/transition） | `addAsset` |
| `track_progress` | 轮询异步生成任务 | 只读 |
| `rerun_generation` | 重跑生成任务 | 重发外部请求 |
| `review_scene_plan` | 多场景计划咨询评审 | 只读 |

### 9. 导出（9 个）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| `submit_export` | 同步导出 MP4/WebM/音频/字幕/FCPXML | 外部渲染 |
| `submit_render_job` | 异步渲染（返回 renderId，进队列） | 外部渲染 |
| `track_export` | 轮询渲染任务状态/进度/下载 | 只读 |
| `read_export_history` | 最近导出历史 | 只读 |
| `verify_export` | 导出 QA（流/时长/黑帧/静音/峰值） | 只读 |
| `export_motion_graphic_prores` | MG → ProRes 4444 .mov（NLE 交接） | 外部渲染 |
| `register_converted_video` | 注册 MG→视频渲染结果为池资产 | `addAsset` |
| `convert_motion_graphic_to_video` | MG 烘焙为真实视频资产 | `replaceMedia` |
| `export_jianying_draft` | 导出剪映/CapCut 草稿（capcut-cli） | 外部 |

### 10. 素材与导入（14 个）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| `list_audio` | 列出音频资产 | 只读 |
| `manage_media_pool` | 媒体池组织（folder/rename/move/favorite/delete/relink） | `pool.*` |
| `download_media` | 从 URL 下载媒体入池 | `addAsset` |
| `push_asset` | 注册公共 URL 为资产 | `addAsset` |
| `import_url_asset` | push_asset 旧别名 | `addAsset` |
| `search_stock_media` | 搜索素材平台 B-roll/图片/音乐 | 只读 |
| `import_media` | 创建上传会话（单次 slot） | 外部握手 |
| `finalize_uploaded_asset` | 完成上传字节（receipt 消费） | `addAsset` |
| `request_asset_download` | 返回下载 URL/path | 只读 |
| `import_asset` | 本地磁盘路径导入（AGENT_IMPORT_ROOTS 白名单） | `addAsset` |
| `import_folder` | 本地目录递归导入 | `addAsset`（批次） |
| `probe_media` | ffprobe 探测（时长/尺寸/fps/码流/风险） | 只读 |
| `edit_asset` | 更新/删除池资产（name/code/props/时间码） | `pool.updateAsset`/`pool.removeAsset` |
| `search_fonts` | 字体目录搜索 | 只读 |

### 11. 其他（35 个）

| 工具 | 用途 | 对应 Action |
|---|---|---|
| `browse_library` | 浏览 OpenChatCut Library（MG/LUT/zoom/fx/audio-fx/SFX/转场） | 只读 |
| `list_templates` / `search_templates` | 模板目录/模糊搜索 | 只读 |
| `manage_design_style` | 设计风格（品牌）list/get/apply/update/clear/save/delete | `design.set`/`design.patch` |
| `manage_template` | 项目模板打包/应用 | `addAsset`/`design.set` 复合 |
| `manage_skill` | 自定义技能 CRUD | 本地持久化 |
| `install_skill` / `run_skill_script` / `load_skill` / `run_code` | 技能安装/脚本执行/加载/沙箱 | 本地/外部 |
| `web_browser` / `web_search` / `web_map` / `web_crawl` / `web_batch_scrape` | Firecrawl 抓取/搜索/地图/爬取/批抓 | 外部 |
| `search_content` | 跨项目全文搜索（FTS5） | 只读 |
| `ask_followup_questions` | 追问卡片（`__followup` 暂停运行时） | 交互 |
| `list_projects` / `create_project` / `delete_project` / `restore_project` / `duplicate_project` / `edit_project` / `target_project` / `get_editor_url` | 项目会话管理 | 项目级持久化 |
| `report_user_friction` | 静默摩擦上报（localStorage 环形缓冲） | 本地 |
| `read_project` | 读当前项目概览 | 只读 |
| `read_agent_artifact` | 读归档工具结果切片（JSON Pointer + 分页） | 只读 |
| `undo_last_change` / `redo_last_change` | 撤销/重做（走提案路径） | `applyDoc` |
| `manage_versions` | 命名版本快照 list/save/restore/delete | `applyDoc` |
| `detect_beats` | 节拍检测（BPM/强拍） | 只读 |
| `analyze_music` / `inspect_music` | Beat This + CLAP 分析/读取 | 只读（可缓存） |
| `music_edit_plan` / `sync_cuts_to_music` | 音乐节奏剪辑计划/执行 | `split` 批次 |
| `music_image_plan` / `sync_images_to_music` | 音乐节奏图片放置计划/执行 | `add` 批次 |
| `inspect_color` | 色彩示波（黑/白点、削波、色偏、直方图） | 只读 |
| `auto_grade` | 技术自动调色（analyze/apply） | `setFilters` |
| `find_highlights` | 长内容 → 竖屏高光片段 | `add`/`tl.duplicate` 复合 |
| `place_graphics_in_safe_zone` | 叠层图形移到安全区（人脸避让） | `setTransform` |
| `view_timeline_frames` / `view_asset_frames` | 渲染帧自检（组合/源） | 只读 |
| `detect_scenes` | FFmpeg 场景检测（标记/切割） | `addMarker`/`split` |
| `ToolSearch` | 关键词发现并激活延迟工具 schema | 只读（激活） |

## 执行分类（execution-policy.ts + execution-modes.ts）

- **effect 分类**（`policyForTool`）：
  - `read`：只读工具（READ_TOOLS 集合 + 外部读 + 全局读）
  - `reversible_edit`：默认，可撤销编辑
  - `persistent_local`：本地持久化（下载/导入/技能/项目/模板/版本）
  - `irreversible_external`：不可逆外部（生成/导出/web/run_code/transcribe）
- **并行分类**（`PARALLEL_TOOL_NAMES`，约 23 个纯读工具可并行）：read_timeline、read_project、list_projects、get_editor_url、list_templates、search_templates、probe_media、search_media、read_transcript、find_transcript、read_script、read_captions、detect_beats、inspect_color、inspect_music、search_content、search_fonts、web_search、ToolSearch、read_agent_artifact、read_export_history、verify_export。其余全部 `exclusive`（串行）。

## 参数 schema 关键字段（按工具类别归纳）

- 所有 `action` 型工具（edit_track / manage_timelines / manage_media_pool / edit_captions / manage_transcript / manage_design_style / manage_template / manage_skill / manage_markers / auto_grade / manage_versions / import_media 等）统一用 `action` 枚举 + 各自的细分字段。
- 片段定位类工具统一用 `itemId`（前缀匹配）+ 可选 `track`（别名或稳定 id）+ `startFrame`/`durationInFrames`/`srcInFrame` + `ripple` 布尔。
- 生成类工具统一 `prompt`/`name` + provider 特有字段（如 submit_voice 的 `provider`/`text`/`voiceId`，submit_video 的 `model`/`durationSeconds`/`resolution`）。
- 时间坐标统一用「帧」（`startFrame`/`fromFrame`/`toFrame`/`durationInFrames`），少数音频类用秒（`fromSeconds`/`toSeconds`），媒体源用 `sourceTimesMs`。

## Caveats / Not Found

- 工具面「核心子集」的圈定建议见本文档末尾「核心子集建议」段，但**最终圈定权在 main agent**（需结合对 78 种 Action 与核心数据模型的判断）。
- 某些工具（如 `submit_image` 系列、`web_*`、`run_code`、`install_skill`）依赖付费/外部服务，迁移到 Python 后端时属于「接口保留但实现可延后」。
- `ask` 目录 22 个工具是 `askOnly` 模式（只读引导）的工具子集，是 edit 目录的子集，不额外增加新工具名。

## 核心子集建议（供 main agent 圈定参考，非决策）

覆盖主要编辑能力、适合第一阶段迁的「核心子集」应包含以下能力域的工具（对应 Action 已在上表给出）：

1. **只读底座**：`read_timeline`、`read_project`、`read_transcript`、`read_script`、`read_captions`、`ToolSearch`、`read_agent_artifact`、`browse_library`、`list_templates`/`search_templates`、`list_audio`。
2. **轨道/时间线**：`edit_track`、`manage_timelines`、`set_aspect_ratio`、`clear_timeline`。
3. **片段编辑核心**：`edit_item`（含全部 item 级 Action）、`add_motion_graphic`、`add_audio`、`update_item_props`、`move_item`、`set_item_timing`、`duplicate_item`、`remove_item`、`split_item`。
4. **文本稿**：`transcribe_track`、`find_transcript`、`clean_script`、`delete_text`、`apply_script`、`manage_transcript`、`search_media`。
5. **字幕**：`edit_captions`、`update_watermark`。
6. **标记**：`manage_markers`。
7. **素材池**：`manage_media_pool`、`edit_asset`、`download_media`、`import_asset`/`import_folder`、`probe_media`。
8. **撤销/版本**：`undo_last_change`、`redo_last_change`、`manage_versions`。

可延后（依赖外部付费服务、重计算、或非核心路径）：
- 生成类全部（submit_image/voice/sound/music/video、submit_motion_graphic、create_motion_graphic_from_code、submit_shader、track_progress、rerun_generation）。
- 导出类（submit_export、submit_render_job、track_export、verify_export、export_motion_graphic_prores、register_converted_video、convert_motion_graphic_to_video、export_jianying_draft）。
- web 抓取 5 个、run_code、install_skill、run_skill_script。
- 高级智能：music_* 6 个、detect_beats、auto_grade、inspect_color、find_highlights、auto_reframe、place_graphics_in_safe_zone、apply_caption_avoidance、detect_scenes、remove_silence、normalize_loudness、isolate_voice、apply_layout、multicam_* 3 个、manage_link_group、search_content、search_fonts、search_stock_media、manage_skill、manage_template、manage_design_style、review_scene_plan。
