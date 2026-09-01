// 命令层：buildCommands 把命令映射为 action（对齐 Python storeCommandBuilder + tool==command）。

import type { Action, SelectMode } from './reduce'
import type {
  CaptionsData,
  ClipEffect,
  ClipFilters,
  ClipTransform,
  Marker,
  MediaAsset,
  MediaFolder,
  MulticamGroup,
  ProjectDoc,
  Timeline,
  TimelineItem,
  TimelineLinkGroup,
  TrackFlags,
  TransitionItem,
  TranscriptVariant,
  TranscriptWord,
  ZoomEffect,
} from './types'

export interface EditorCommands {
  // 骨架既有
  addItem(item: TimelineItem): void
  removeItem(itemId: string): void
  clearTimeline(): void
  duplicateItem(itemId: string, newId: string): void
  splitItem(itemId: string, atFrame: number, newId: string): void
  moveItem(itemId: string, track?: string, startFrame?: number): void
  retimeItem(itemId: string, opts: { startFrame?: number; durationInFrames?: number; srcInFrame?: number }): void
  setItemVolume(itemId: string, volume: number): void
  setItemTransform(itemId: string, patch: Partial<ClipTransform>): void
  addTransition(transition: TransitionItem): void
  undo(): void
  redo(): void

  // 轨道（4）
  createTrack(trackId: string, kind: string, name?: string, order?: number): void
  updateTrack(trackId: string, patch: Partial<TrackFlags>): void
  deleteTrack(trackId: string): void
  toggleTrackFlag(trackId: string, flag: string, value: boolean): void

  // 片段基础 + 属性
  updateItemProps(itemId: string, patch: Partial<TimelineItem>): void
  setItemFade(itemId: string, opts: { fadeInFrames?: number; fadeOutFrames?: number }): void
  setItemFilters(itemId: string, patch: Partial<ClipFilters>): void
  setItemSpeed(itemId: string, rate: number): void
  setItemZoom(itemId: string, patch: Partial<ZoomEffect>): void
  setItemEffects(itemId: string, effects: ClipEffect[]): void

  // 转场（2）
  setTransition(transitionId: string, patch: Partial<TransitionItem>): void
  removeTransition(transitionId: string): void

  // 字幕（3）
  setCaptions(captions: CaptionsData | null): void
  updateCaptions(patch: Partial<CaptionsData>): void
  setCaptionsHidden(hidden: boolean): void

  // 关键帧（3）
  setKeyframe(itemId: string, prop: string, frame: number, value: number, easing?: string): void
  removeKeyframe(itemId: string, prop: string, frame: number): void
  clearKeyframes(itemId: string, prop?: string): void

  // 标记（3）
  addMarker(marker: Marker): void
  updateMarker(markerId: string, patch: Partial<Marker>): void
  removeMarker(markerId: string): void

  // 选择（3）
  select(itemId: string | null, mode?: SelectMode): void
  selectMany(ids: string[]): void
  selectAll(): void

  // 素材池（4）
  addAsset(asset: MediaAsset): void
  createFolder(folder: MediaFolder): void
  moveAssets(ids: string[], folderId?: string): void
  removeAsset(assetId: string): void

  // 片段属性补充（8）
  slipItem(itemId: string, deltaInFrames: number): void
  setBackgroundFill(itemId: string, enabled: boolean, strength?: number): void
  replaceMedia(itemId: string, src: string): void
  relinkItem(itemId: string, opts: { src?: string; sourceAssetId?: string; sourceRevision?: string }): void
  updateWatermark(opts: { enabled?: boolean; text?: string; position?: string; opacity?: number; fontSize?: number; color?: string; margin?: number }): void
  setItemDenoise(itemId: string, denoisedSrc: string | null, strength?: number): void
  setReframeKeyframe(itemId: string, frame: number, focalPointX: number, focalPointY: number, magnification: number): void
  removeReframeKeyframe(itemId: string, frame: number): void

  // 转写（12）
  setItemTranscript(itemId: string, transcript: TranscriptWord[], generationId?: string): void
  setItemVariants(itemId: string, variants: TranscriptVariant[]): void
  toggleWord(itemId: string, idx: number): void
  deleteWords(itemId: string, idxs: number[]): void
  cleanScript(itemId: string, opts: { removeFillers?: boolean; silenceFrames?: number; cutPadFrames?: number }): void
  setGapCap(itemId: string, afterWordIdx: number, maxMs: number | null): void
  setTranscriptPlayOrder(itemId: string, playOrder: number[] | null): void
  reorderTrackItems(track: string, orderedIds: string[], starts?: Record<string, number>): void
  clearEdits(itemId: string): void
  fixTranscriptWord(itemId: string, wordIdx: number, text: string): void
  renameSpeaker(itemId: string, fromSpeaker: string, toSpeaker: string): void
  setAssetTranscription(assetId: string, transcript: TranscriptWord[], sourceRevision?: string): void

  // 项目级（16）
  createTimeline(timeline: Timeline, activate?: boolean): void
  switchTimeline(timelineId: string): void
  duplicateTimeline(timelineId: string, newId: string, name: string): void
  deleteTimeline(timelineId: string): void
  renameTimeline(timelineId: string, name: string): void
  retargetTimeline(timelineId: string, width: number, height: number, fit?: string): void
  setTimelineHidden(timelineId: string, hidden: boolean): void
  setProjectDoc(doc: ProjectDoc): void
  renameFolder(folderId: string, name: string): void
  deleteFolder(folderId: string): void
  updateAsset(assetId: string, patch: Partial<MediaAsset>): void
  relinkAsset(assetId: string, src: string): void
  canonicalizeAsset(duplicateId: string, canonicalId: string): void
  setDesignStyle(style: Record<string, unknown> | null): void
  patchDesignStyle(patch: Record<string, unknown>): void
  setFullState(patch: Partial<Timeline>): void

  // 多机位（6）
  tightenTrack(track: string): void
  setCanvas(width: number, height: number, fit?: string): void
  setMulticamGroups(groups: MulticamGroup[]): void
  addMulticamDecision(groupId: string, fromFrame: number, toFrame: number, angleId: string, decisionId?: string): void
  setLinkGroups(groups: TimelineLinkGroup[]): void
  addLinkGroup(group: TimelineLinkGroup): void
}

export function buildCommands(dispatch: (a: Action) => void): EditorCommands {
  return {
    // 骨架既有
    addItem: (item) => dispatch({ type: 'add_item', item }),
    removeItem: (itemId) => dispatch({ type: 'remove_item', itemId }),
    clearTimeline: () => dispatch({ type: 'clear_timeline' }),
    duplicateItem: (itemId, newId) => dispatch({ type: 'duplicate_item', itemId, newId }),
    splitItem: (itemId, atFrame, newId) => dispatch({ type: 'split_item', itemId, atFrame, newId }),
    moveItem: (itemId, track, startFrame) => dispatch({ type: 'move_item', itemId, track, startFrame }),
    retimeItem: (itemId, opts) => dispatch({ type: 'retime_item', itemId, ...opts }),
    setItemVolume: (itemId, volume) => dispatch({ type: 'set_item_volume', itemId, volume }),
    setItemTransform: (itemId, patch) => dispatch({ type: 'set_item_transform', itemId, patch }),
    addTransition: (transition) => dispatch({ type: 'add_transition', transition }),
    undo: () => dispatch({ type: 'undo' }),
    redo: () => dispatch({ type: 'redo' }),

    // 轨道
    createTrack: (trackId, kind, name, order) => dispatch({ type: 'create_track', trackId, kind, name, order }),
    updateTrack: (trackId, patch) => dispatch({ type: 'update_track', trackId, patch }),
    deleteTrack: (trackId) => dispatch({ type: 'delete_track', trackId }),
    toggleTrackFlag: (trackId, flag, value) => dispatch({ type: 'toggle_track_flag', trackId, flag, value }),

    // 片段基础 + 属性
    updateItemProps: (itemId, patch) => dispatch({ type: 'update_item_props', itemId, patch }),
    setItemFade: (itemId, opts) => dispatch({ type: 'set_item_fade', itemId, ...opts }),
    setItemFilters: (itemId, patch) => dispatch({ type: 'set_item_filters', itemId, patch }),
    setItemSpeed: (itemId, rate) => dispatch({ type: 'set_item_speed', itemId, rate }),
    setItemZoom: (itemId, patch) => dispatch({ type: 'set_item_zoom', itemId, patch }),
    setItemEffects: (itemId, effects) => dispatch({ type: 'set_item_effects', itemId, effects }),

    // 转场
    setTransition: (transitionId, patch) => dispatch({ type: 'set_transition', transitionId, patch }),
    removeTransition: (transitionId) => dispatch({ type: 'remove_transition', transitionId }),

    // 字幕
    setCaptions: (captions) => dispatch({ type: 'set_captions', captions }),
    updateCaptions: (patch) => dispatch({ type: 'update_captions', patch }),
    setCaptionsHidden: (hidden) => dispatch({ type: 'set_captions_hidden', hidden }),

    // 关键帧
    setKeyframe: (itemId, prop, frame, value, easing) => dispatch({ type: 'set_keyframe', itemId, prop, frame, value, easing }),
    removeKeyframe: (itemId, prop, frame) => dispatch({ type: 'remove_keyframe', itemId, prop, frame }),
    clearKeyframes: (itemId, prop) => dispatch({ type: 'clear_keyframes', itemId, prop }),

    // 标记
    addMarker: (marker) => dispatch({ type: 'add_marker', marker }),
    updateMarker: (markerId, patch) => dispatch({ type: 'update_marker', markerId, patch }),
    removeMarker: (markerId) => dispatch({ type: 'remove_marker', markerId }),

    // 选择
    select: (itemId, mode) => dispatch({ type: 'select', itemId, mode }),
    selectMany: (ids) => dispatch({ type: 'select_many', ids }),
    selectAll: () => dispatch({ type: 'select_all' }),

    // 素材池
    addAsset: (asset) => dispatch({ type: 'add_asset', asset }),
    createFolder: (folder) => dispatch({ type: 'create_folder', folder }),
    moveAssets: (ids, folderId) => dispatch({ type: 'move_assets', ids, folderId }),
    removeAsset: (assetId) => dispatch({ type: 'remove_asset', assetId }),

    // 片段属性补充
    slipItem: (itemId, deltaInFrames) => dispatch({ type: 'slip_item', itemId, deltaInFrames }),
    setBackgroundFill: (itemId, enabled, strength) => dispatch({ type: 'set_background_fill', itemId, enabled, strength }),
    replaceMedia: (itemId, src) => dispatch({ type: 'replace_media', itemId, src }),
    relinkItem: (itemId, opts) => dispatch({ type: 'relink_item', itemId, ...opts }),
    updateWatermark: (opts) => dispatch({ type: 'update_watermark', ...opts }),
    setItemDenoise: (itemId, denoisedSrc, strength) => dispatch({ type: 'set_item_denoise', itemId, denoisedSrc, strength }),
    setReframeKeyframe: (itemId, frame, focalPointX, focalPointY, magnification) =>
      dispatch({ type: 'set_reframe_keyframe', itemId, frame, focalPointX, focalPointY, magnification }),
    removeReframeKeyframe: (itemId, frame) => dispatch({ type: 'remove_reframe_keyframe', itemId, frame }),

    // 转写
    setItemTranscript: (itemId, transcript, generationId) => dispatch({ type: 'set_item_transcript', itemId, transcript, generationId }),
    setItemVariants: (itemId, variants) => dispatch({ type: 'set_item_variants', itemId, variants }),
    toggleWord: (itemId, idx) => dispatch({ type: 'toggle_word', itemId, idx }),
    deleteWords: (itemId, idxs) => dispatch({ type: 'delete_words', itemId, idxs }),
    cleanScript: (itemId, opts) => dispatch({ type: 'clean_script', itemId, ...opts }),
    setGapCap: (itemId, afterWordIdx, maxMs) => dispatch({ type: 'set_gap_cap', itemId, afterWordIdx, maxMs }),
    setTranscriptPlayOrder: (itemId, playOrder) => dispatch({ type: 'set_transcript_play_order', itemId, playOrder }),
    reorderTrackItems: (track, orderedIds, starts) => dispatch({ type: 'reorder_track_items', track, orderedIds, starts }),
    clearEdits: (itemId) => dispatch({ type: 'clear_edits', itemId }),
    fixTranscriptWord: (itemId, wordIdx, text) => dispatch({ type: 'fix_transcript_word', itemId, wordIdx, text }),
    renameSpeaker: (itemId, fromSpeaker, toSpeaker) => dispatch({ type: 'rename_speaker', itemId, fromSpeaker, toSpeaker }),
    setAssetTranscription: (assetId, transcript, sourceRevision) =>
      dispatch({ type: 'set_asset_transcription', assetId, transcript, sourceRevision }),

    // 项目级
    createTimeline: (timeline, activate) => dispatch({ type: 'create_timeline', timeline, activate }),
    switchTimeline: (timelineId) => dispatch({ type: 'switch_timeline', timelineId }),
    duplicateTimeline: (timelineId, newId, name) => dispatch({ type: 'duplicate_timeline', timelineId, newId, name }),
    deleteTimeline: (timelineId) => dispatch({ type: 'delete_timeline', timelineId }),
    renameTimeline: (timelineId, name) => dispatch({ type: 'rename_timeline', timelineId, name }),
    retargetTimeline: (timelineId, width, height, fit) => dispatch({ type: 'retarget_timeline', timelineId, width, height, fit }),
    setTimelineHidden: (timelineId, hidden) => dispatch({ type: 'set_timeline_hidden', timelineId, hidden }),
    setProjectDoc: (doc) => dispatch({ type: 'set_project_doc', doc }),
    renameFolder: (folderId, name) => dispatch({ type: 'rename_folder', folderId, name }),
    deleteFolder: (folderId) => dispatch({ type: 'delete_folder', folderId }),
    updateAsset: (assetId, patch) => dispatch({ type: 'update_asset', assetId, patch }),
    relinkAsset: (assetId, src) => dispatch({ type: 'relink_asset', assetId, src }),
    canonicalizeAsset: (duplicateId, canonicalId) => dispatch({ type: 'canonicalize_asset', duplicateId, canonicalId }),
    setDesignStyle: (style) => dispatch({ type: 'set_design_style', style }),
    patchDesignStyle: (patch) => dispatch({ type: 'patch_design_style', patch }),
    setFullState: (patch) => dispatch({ type: 'set_full_state', patch }),

    // 多机位
    tightenTrack: (track) => dispatch({ type: 'tighten_track', track }),
    setCanvas: (width, height, fit) => dispatch({ type: 'set_canvas', width, height, fit }),
    setMulticamGroups: (groups) => dispatch({ type: 'set_multicam_groups', groups }),
    addMulticamDecision: (groupId, fromFrame, toFrame, angleId, decisionId) =>
      dispatch({ type: 'add_multicam_decision', groupId, fromFrame, toFrame, angleId, decisionId }),
    setLinkGroups: (groups) => dispatch({ type: 'set_link_groups', groups }),
    addLinkGroup: (group) => dispatch({ type: 'add_link_group', group }),
  }
}

export function newId(): string {
  return crypto.randomUUID().slice(0, 8)
}
