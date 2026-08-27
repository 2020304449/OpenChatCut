# 技术设计 — 后端迁移 A-2（补全编辑命令）

## 1. 架构延续

沿用 A-1 的全部架构决策（单体后端、帧单位、frozen dataclass、命令层 + 快照撤销、细粒度工具）。A-2 只做**增量**：扩展数据模型 + 补命令 + 补工具，不改既有 38 种命令的契约。

## 2. 数据模型扩展（transcript 词级）

新增 `app/domain/transcript.py`：

```python
@dataclass(frozen=True)
class TranscriptWord:
    id: str | None = None
    text: str = ""
    startMs: int = 0      # 毫秒（对齐源码）
    endMs: int = 0
    speaker: str | None = None   # 'A' | 'B' | ...

@dataclass(frozen=True)
class TranscriptVariantWord:
    i: int                 # 源词索引（sparse overlay）
    text: str

@dataclass(frozen=True)
class TranscriptVariant:
    id: str
    lang: str
    kind: str              # 'translation' | 'corrected'
    label: str
    words: tuple[TranscriptVariantWord, ...] = ()
```

`TimelineItem` 扩展字段（`app/domain/item.py`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| transcript | `tuple[TranscriptWord, ...] \| None` | 词级转写（ms） |
| transcriptGenerationId | `str \| None` | 每次重转写变化，防旧词引用错位 |
| transcriptStale | `bool` | 过期的转写只读、不驱动播放/编辑 |
| variants | `tuple[TranscriptVariant, ...]` | 翻译/修正变体 |
| deletedWordIdx | `tuple[int, ...]` | 已删除词的源索引 |
| silenceFrames | `int \| None` | 词间停顿压缩上限（帧） |
| cutPadFrames | `int \| None` | 删词边界两侧保留帧 |
| gapCapsMs | `dict[str, int]` | per-gap 上限（key=gap 后词索引） |
| transcriptPlayOrder | `tuple[int, ...] \| None` | 播放顺序（源词索引） |

**关键决策**：transcript 时间戳用 **ms**（对齐源码 `src/transcript/types.ts`），clip 用帧。转换函数：

```python
def ms_to_frame(ms: int, fps: int) -> int:
    return round(ms / 1000 * fps)
```

## 3. 命令清单（35 种增量）

### 文本稿词级（12）
| 命令 | 作用 | 关键逻辑 |
|---|---|---|
| SetItemTranscript | 设置词级转写 | 直接替换 transcript + generationId |
| SetItemVariants | 设置翻译变体 | 替换 variants |
| ToggleWord | 切换词删除状态 | deletedWordIdx 增删 idx |
| DeleteWords | 删除词 | deletedWordIdx 合并 idxs |
| CleanScript | 清理脚本 | 移除填充词 + 按 silenceFrames 压缩停顿 + cutPad |
| SetGapCap | 设置间隙上限 | gapCapsMs[idx]=maxMs |
| SetTranscriptPlayOrder | 设置播放顺序 | transcriptPlayOrder |
| ReorderTrackItems | 重排轨道项 | 按 orderedIds 重排，starts 可选 pin 绝对帧 |
| ClearEdits | 清除转写编辑 | 清 deletedWordIdx/gapCapsMs/playOrder/variants |
| FixTranscriptWord | 修正词文本 | transcript[idx].text = text |
| RenameSpeaker | 重命名说话人 | 遍历 transcript 改 speaker |
| PoolSetTranscription | 素材转写 | 更新 MediaAsset 的 transcript 字段 |

### 剩余片段属性（8）
| 命令 | 作用 |
|---|---|
| SlipItem | 平移源窗口（srcInFrame 增量） |
| SetBackgroundFill | 背景填充开关/强度 |
| ReplaceMedia | 替换片段媒体 src |
| RelinkTimelineItem | 重新链接（src + sourceAssetId + revision） |
| UpdateWatermark | 水印开关/文本/位置/不透明度 |
| SetItemDenoise | 降噪（denoisedSrc + strength） |
| SetReframeKeyframe | reframe 关键帧 |
| RemoveReframeKeyframe | 移除 reframe 关键帧 |

### 项目级（~15）
| 命令 | 作用 |
|---|---|
| TimelineCreate / Switch / Duplicate / Delete / Rename / Retarget / SetHidden / SetDoc | 多时间线管理 |
| PoolRenameFolder / DeleteFolder / UpdateAsset / RelinkAsset / CanonicalizeAsset | 素材池完整 |
| SetDesignStyle / PatchDesignStyle | 品牌设计风格 |
| SetFullState | 整体替换 TimelineState |

## 4. cleanScript 算法（简化版）

```
输入：removeFillers, silenceFrames, cutPadFrames
1. 遍历 transcript，标记填充词（"um"/"uh"/"呃"/"嗯"/"那个"/"这个"...）
   → 加入 deletedWordIdx
2. 压缩词间停顿：相邻保留词之间 gap > silenceFrames 时，gap 截断为 silenceFrames
   → 重算每个词的时间轴（ms）
3. cutPadFrames：删除词边界两侧各保留 cutPadFrames/2 帧的原始停顿
4. 更新 item.transcript（新时间轴）+ deletedWordIdx + silenceFrames + cutPadFrames
```

（真实 OpenChatCut 的 cleanScript 还有 gapCapsMs per-gap 覆盖、呼吸保留等细节，A-2 实现核心版本，细节留待后续。）

## 5. 工具面（约 15~20 个新增）

对齐 OpenChatCut 文本稿工具命名：

| 工具 | 对应命令 |
|---|---|
| transcribe_track | SetItemTranscript / PoolSetTranscription |
| read_transcript | （只读，读 transcript） |
| find_transcript | （只读，定位短语） |
| clean_script | CleanScript |
| delete_text | DeleteWords |
| manage_transcript | FixTranscriptWord / SetItemVariants / RenameSpeaker |
| read_script | （只读，物化 timeline.md，A-2 简化） |
| edit_item（扩展） | slip / replaceMedia / setBackgroundFill / setItemDenoise 等 |

其余片段属性 + 项目级命令，沿用 A-1 的细粒度工具风格（`slip_item` / `set_background_fill` / `manage_timelines` / `manage_media_pool` 扩展 / `set_design_style` / `set_full_state` 等）。

## 6. 延后项追踪（[DEFERRED] 标记）

统一标记 `[DEFERRED]`，文档 + 代码两处记录，grep `DEFERRED` 即可找到全部延后项：

| [DEFERRED] 项 | 依赖 | 后续阶段 |
|---|---|---|
| 生成类工具（submit_image/voice/music/video 等 10 个） | 外部付费服务 | 阶段 C |
| 导出类工具（submit_export/render_job 等 8 个） | 渲染引擎 Remotion/FFmpeg | 阶段 C/D |
| 高级智能（multicam/linkGroups/音乐节奏/调色/场景检测/高光/reframe 自动/人脸避让） | 重计算/外部模型 | 按需 |

代码侧：在 `app/agent/tools.py` 顶部加一个 `DEFERRED_TOOLS` 注释块，列出延后工具名 + 依赖，便于 grep。

## 7. 风险与回滚

| 风险 | 应对 |
|---|---|
| ms vs 帧换算错 | `ms_to_frame` 单点封装 + 测试（30fps 下 1000ms=30 帧） |
| cleanScript 算法边界（空 transcript、单词、相邻填充词） | 单测覆盖边界；算法简化并在代码注释标注与源码差异 |
| 项目级命令影响 activeTimeline 路由 | tl.switch 是导航不产生历史；tl.* 落 ProjectDoc 顶层，测试覆盖 |
| 字段膨胀（TimelineItem 30+ 字段） | frozen dataclass + 默认值，保持 to_dict 往返无损 |
