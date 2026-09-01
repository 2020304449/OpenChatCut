// 编辑器 reducer（对齐 Python commands/actions.py + commands/base.py）。
//
// action 类型名 = Python 命令类名 snake_case，字段名 camelCase。
// projectReduce 是纯函数：绝不原地改 doc，找不到目标 id 时返回原 doc（无效动作不进历史）。

import type {
  CaptionsData,
  ClipEffect,
  ClipFilters,
  ClipTransform,
  Keyframe,
  Marker,
  MediaAsset,
  MediaFolder,
  MulticamAngleDecision,
  MulticamGroup,
  ProjectDoc,
  Timeline,
  TimelineItem,
  TimelineLinkGroup,
  TrackFlags,
  TransitionItem,
  TranscriptVariant,
  TranscriptWord,
  Watermark,
  ZoomEffect,
} from './types'
import { activeTimeline } from './types'

// ── action 类型（全部命令） ──────────────────────────────────────────────

export type SelectMode = 'replace' | 'toggle' | 'add'

export type EditAction =
  // 轨道（4）
  | { type: 'create_track'; trackId: string; kind: string; name?: string; order?: number }
  | { type: 'update_track'; trackId: string; patch: Partial<TrackFlags> }
  | { type: 'delete_track'; trackId: string }
  | { type: 'toggle_track_flag'; trackId: string; flag: string; value: boolean }
  // 片段基础（骨架 4 条 + update_item_props）
  | { type: 'add_item'; item: TimelineItem }
  | { type: 'remove_item'; itemId: string }
  | { type: 'clear_timeline' }
  | { type: 'duplicate_item'; itemId: string; newId: string }
  | { type: 'split_item'; itemId: string; atFrame: number; newId: string }
  | { type: 'move_item'; itemId: string; track?: string; startFrame?: number }
  | { type: 'retime_item'; itemId: string; startFrame?: number; durationInFrames?: number; srcInFrame?: number }
  | { type: 'update_item_props'; itemId: string; patch: Partial<TimelineItem> }
  // 片段属性（5）
  | { type: 'set_item_fade'; itemId: string; fadeInFrames?: number; fadeOutFrames?: number }
  | { type: 'set_item_filters'; itemId: string; patch: Partial<ClipFilters> }
  | { type: 'set_item_speed'; itemId: string; rate: number }
  | { type: 'set_item_zoom'; itemId: string; patch: Partial<ZoomEffect> }
  | { type: 'set_item_effects'; itemId: string; effects: ClipEffect[] }
  // 片段属性（骨架既有）+ 转场
  | { type: 'set_item_volume'; itemId: string; volume: number }
  | { type: 'set_item_transform'; itemId: string; patch: Partial<ClipTransform> }
  | { type: 'add_transition'; transition: TransitionItem }
  | { type: 'set_transition'; transitionId: string; patch: Partial<TransitionItem> }
  | { type: 'remove_transition'; transitionId: string }
  // 字幕（3）
  | { type: 'set_captions'; captions: CaptionsData | null }
  | { type: 'update_captions'; patch: Partial<CaptionsData> }
  | { type: 'set_captions_hidden'; hidden: boolean }
  // 关键帧（3）
  | { type: 'set_keyframe'; itemId: string; prop: string; frame: number; value: number; easing?: string }
  | { type: 'remove_keyframe'; itemId: string; prop: string; frame: number }
  | { type: 'clear_keyframes'; itemId: string; prop?: string }
  // 标记（3）
  | { type: 'add_marker'; marker: Marker }
  | { type: 'update_marker'; markerId: string; patch: Partial<Marker> }
  | { type: 'remove_marker'; markerId: string }
  // 选择（3）
  | { type: 'select'; itemId: string | null; mode?: SelectMode }
  | { type: 'select_many'; ids: string[] }
  | { type: 'select_all' }
  // 素材池（4）
  | { type: 'add_asset'; asset: MediaAsset }
  | { type: 'create_folder'; folder: MediaFolder }
  | { type: 'move_assets'; ids: string[]; folderId?: string }
  | { type: 'remove_asset'; assetId: string }
  // 片段属性补充（8）
  | { type: 'slip_item'; itemId: string; deltaInFrames: number }
  | { type: 'set_background_fill'; itemId: string; enabled: boolean; strength?: number }
  | { type: 'replace_media'; itemId: string; src: string }
  | { type: 'relink_item'; itemId: string; src?: string; sourceAssetId?: string; sourceRevision?: string }
  | { type: 'update_watermark'; enabled?: boolean; text?: string; position?: string; opacity?: number; fontSize?: number; color?: string; margin?: number }
  | { type: 'set_item_denoise'; itemId: string; denoisedSrc: string | null; strength?: number }
  | { type: 'set_reframe_keyframe'; itemId: string; frame: number; focalPointX: number; focalPointY: number; magnification: number }
  | { type: 'remove_reframe_keyframe'; itemId: string; frame: number }
  // 转写（12）
  | { type: 'set_item_transcript'; itemId: string; transcript: TranscriptWord[]; generationId?: string }
  | { type: 'set_item_variants'; itemId: string; variants: TranscriptVariant[] }
  | { type: 'toggle_word'; itemId: string; idx: number }
  | { type: 'delete_words'; itemId: string; idxs: number[] }
  | { type: 'clean_script'; itemId: string; removeFillers?: boolean; silenceFrames?: number; cutPadFrames?: number }
  | { type: 'set_gap_cap'; itemId: string; afterWordIdx: number; maxMs: number | null }
  | { type: 'set_transcript_play_order'; itemId: string; playOrder: number[] | null }
  | { type: 'reorder_track_items'; track: string; orderedIds: string[]; starts?: Record<string, number> }
  | { type: 'clear_edits'; itemId: string }
  | { type: 'fix_transcript_word'; itemId: string; wordIdx: number; text: string }
  | { type: 'rename_speaker'; itemId: string; fromSpeaker: string; toSpeaker: string }
  | { type: 'set_asset_transcription'; assetId: string; transcript: TranscriptWord[]; sourceRevision?: string }
  // 项目级（16）
  | { type: 'create_timeline'; timeline: Timeline; activate?: boolean }
  | { type: 'switch_timeline'; timelineId: string }
  | { type: 'duplicate_timeline'; timelineId: string; newId: string; name: string }
  | { type: 'delete_timeline'; timelineId: string }
  | { type: 'rename_timeline'; timelineId: string; name: string }
  | { type: 'retarget_timeline'; timelineId: string; width: number; height: number; fit?: string }
  | { type: 'set_timeline_hidden'; timelineId: string; hidden: boolean }
  | { type: 'set_project_doc'; doc: ProjectDoc }
  | { type: 'rename_folder'; folderId: string; name: string }
  | { type: 'delete_folder'; folderId: string }
  | { type: 'update_asset'; assetId: string; patch: Partial<MediaAsset> }
  | { type: 'relink_asset'; assetId: string; src: string }
  | { type: 'canonicalize_asset'; duplicateId: string; canonicalId: string }
  | { type: 'set_design_style'; style: Record<string, unknown> | null }
  | { type: 'patch_design_style'; patch: Record<string, unknown> }
  | { type: 'set_full_state'; patch: Partial<Timeline> }
  // 多机位（6）
  | { type: 'tighten_track'; track: string }
  | { type: 'set_canvas'; width: number; height: number; fit?: string }
  | { type: 'set_multicam_groups'; groups: MulticamGroup[] }
  | { type: 'add_multicam_decision'; groupId: string; fromFrame: number; toFrame: number; angleId: string; decisionId?: string }
  | { type: 'set_link_groups'; groups: TimelineLinkGroup[] }
  | { type: 'add_link_group'; group: TimelineLinkGroup }

export type Action = EditAction | { type: 'undo' } | { type: 'redo' }

// ── 填充词（对齐 transcript_actions.FILLER_WORDS） ──────────────────────

const FILLER_WORDS = new Set([
  'um', 'uh', 'er', '呃', '嗯', '啊', '那个', '这个', '就是', '然后', '然后呢', '对吧',
])

function genId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID().slice(0, 8)
  return Math.random().toString(36).slice(2, 10)
}

// ── 作用域路由 helper（对齐 _map_active / _map_item） ─────────────────────

function mapActive(doc: ProjectDoc, fn: (tl: Timeline) => Timeline): ProjectDoc {
  const tl = activeTimeline(doc)
  const newTl = fn(tl)
  if (newTl === tl) return doc // 未变化 → 原 doc（无效动作不进历史）
  return { ...doc, timelines: doc.timelines.map((t) => (t.id === tl.id ? newTl : t)) }
}

function mapItem(doc: ProjectDoc, itemId: string, fn: (it: TimelineItem) => TimelineItem): ProjectDoc {
  const tl = activeTimeline(doc)
  if (!tl.items.some((i) => i.id === itemId)) return doc // 找不到 → 原 doc（无效动作不进历史）
  return mapActive(doc, (t) => ({ ...t, items: t.items.map((i) => (i.id === itemId ? fn(i) : i)) }))
}

// ── projectReduce（纯函数，无副作用） ─────────────────────────────────────

export function projectReduce(doc: ProjectDoc, action: EditAction): ProjectDoc {
  switch (action.type) {
    // ── 轨道 ──
    case 'create_track':
      return mapActive(doc, (tl) => {
        const flags: TrackFlags = { kind: action.kind, name: action.name }
        const tracks = { ...(tl.tracks ?? {}), [action.trackId]: flags }
        const order = [...(tl.trackOrder ?? [])]
        if (!order.includes(action.trackId)) {
          if (action.order !== undefined && action.order >= 0 && action.order < order.length) {
            order.splice(action.order, 0, action.trackId)
          } else {
            order.push(action.trackId)
          }
        }
        return { ...tl, tracks, trackOrder: order }
      })

    case 'update_track':
      return mapActive(doc, (tl) => {
        const cur = tl.tracks?.[action.trackId] ?? {}
        return { ...tl, tracks: { ...(tl.tracks ?? {}), [action.trackId]: { ...cur, ...action.patch } } }
      })

    case 'delete_track':
      return mapActive(doc, (tl) => {
        const tracks: Record<string, TrackFlags> = {}
        for (const [k, v] of Object.entries(tl.tracks ?? {})) if (k !== action.trackId) tracks[k] = v
        return {
          ...tl,
          tracks,
          trackOrder: (tl.trackOrder ?? []).filter((t) => t !== action.trackId),
          items: tl.items.filter((i) => i.track !== action.trackId),
        }
      })

    case 'toggle_track_flag':
      return mapActive(doc, (tl) => {
        const cur = tl.tracks?.[action.trackId] ?? {}
        return { ...tl, tracks: { ...(tl.tracks ?? {}), [action.trackId]: { ...cur, [action.flag]: action.value } } }
      })

    // ── 片段基础 ──
    case 'add_item':
      return mapActive(doc, (tl) => ({ ...tl, items: [...tl.items, action.item] }))

    case 'remove_item':
      return mapActive(doc, (tl) => ({
        ...tl,
        items: tl.items.filter((i) => i.id !== action.itemId),
        transitions: tl.transitions.filter(
          (t) => t.incomingItemId !== action.itemId && t.id !== action.itemId,
        ),
      }))

    case 'clear_timeline':
      return mapActive(doc, (tl) => ({ ...tl, items: [], transitions: [], selectedId: null, selectedIds: [] }))

    case 'duplicate_item':
      return mapActive(doc, (tl) => {
        const out: TimelineItem[] = []
        for (const it of tl.items) {
          out.push(it)
          if (it.id === action.itemId) {
            out.push({ ...it, id: action.newId, startFrame: it.startFrame + it.durationInFrames })
          }
        }
        return { ...tl, items: out }
      })

    case 'split_item':
      return mapActive(doc, (tl) => {
        const out: TimelineItem[] = []
        for (const it of tl.items) {
          if (it.id !== action.itemId) {
            out.push(it)
            continue
          }
          const { startFrame, durationInFrames } = it
          if (action.atFrame <= startFrame || action.atFrame >= startFrame + durationInFrames) {
            out.push(it) // 分割点越界，保持原样
            continue
          }
          const leftDur = action.atFrame - startFrame
          out.push({ ...it, durationInFrames: leftDur })
          out.push({ ...it, id: action.newId, startFrame: action.atFrame, durationInFrames: durationInFrames - leftDur })
        }
        return { ...tl, items: out }
      })

    case 'move_item': {
      const patch: Partial<TimelineItem> = {}
      if (action.track !== undefined) patch.track = action.track
      if (action.startFrame !== undefined) patch.startFrame = action.startFrame
      return mapItem(doc, action.itemId, (it) => ({ ...it, ...patch }))
    }

    case 'retime_item': {
      const patch: Partial<TimelineItem> = {}
      if (action.startFrame !== undefined) patch.startFrame = action.startFrame
      if (action.durationInFrames !== undefined) patch.durationInFrames = action.durationInFrames
      if (action.srcInFrame !== undefined) patch.srcInFrame = action.srcInFrame
      return mapItem(doc, action.itemId, (it) => ({ ...it, ...patch }))
    }

    case 'update_item_props':
      return mapItem(doc, action.itemId, (it) => ({ ...it, ...action.patch }))

    // ── 片段属性 ──
    case 'set_item_volume':
      return mapItem(doc, action.itemId, (it) => ({ ...it, volume: action.volume }))

    case 'set_item_transform':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        transform: { ...(it.transform ?? {}), ...action.patch },
      }))

    case 'set_item_fade': {
      const patch: Partial<TimelineItem> = {}
      if (action.fadeInFrames !== undefined) patch.fadeInFrames = action.fadeInFrames
      if (action.fadeOutFrames !== undefined) patch.fadeOutFrames = action.fadeOutFrames
      return mapItem(doc, action.itemId, (it) => ({ ...it, ...patch }))
    }

    case 'set_item_filters':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        filters: { ...(it.filters ?? {}), ...action.patch },
      }))

    case 'set_item_speed':
      return mapItem(doc, action.itemId, (it) => ({ ...it, playbackRate: action.rate }))

    case 'set_item_zoom':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        zoom: { ...(it.zoom ?? {}), ...action.patch },
      }))

    case 'set_item_effects':
      return mapItem(doc, action.itemId, (it) => ({ ...it, effects: action.effects }))

    // ── 转场 ──
    case 'add_transition':
      return mapActive(doc, (tl) => ({ ...tl, transitions: [...tl.transitions, action.transition] }))

    case 'set_transition': {
      const tl = activeTimeline(doc)
      if (!tl.transitions.some((t) => t.id === action.transitionId)) return doc
      return mapActive(doc, (t) => ({
        ...t,
        transitions: t.transitions.map((tr) => (tr.id === action.transitionId ? { ...tr, ...action.patch } : tr)),
      }))
    }

    case 'remove_transition': {
      const tl = activeTimeline(doc)
      if (!tl.transitions.some((t) => t.id === action.transitionId)) return doc
      return mapActive(doc, (t) => ({ ...t, transitions: t.transitions.filter((tr) => tr.id !== action.transitionId) }))
    }

    // ── 字幕 ──
    case 'set_captions':
      return mapActive(doc, (tl) => ({ ...tl, captions: action.captions }))

    case 'update_captions':
      return mapActive(doc, (tl) => {
        const cur = tl.captions ?? { enabled: true, items: [] }
        return { ...tl, captions: { ...cur, ...action.patch } }
      })

    case 'set_captions_hidden':
      return mapActive(doc, (tl) => ({ ...tl, captionsHidden: action.hidden }))

    // ── 关键帧 ──
    case 'set_keyframe':
      return mapItem(doc, action.itemId, (it) => {
        const curves: Record<string, Keyframe[]> = { ...(it.keyframes ?? {}) }
        const kfs = (curves[action.prop] ?? []).filter((k) => k.frame !== action.frame)
        kfs.push({ frame: action.frame, value: action.value, easing: action.easing ?? null })
        kfs.sort((a, b) => a.frame - b.frame)
        curves[action.prop] = kfs
        return { ...it, keyframes: curves }
      })

    case 'remove_keyframe':
      return mapItem(doc, action.itemId, (it) => {
        const curves: Record<string, Keyframe[]> = { ...(it.keyframes ?? {}) }
        const kfs = (curves[action.prop] ?? []).filter((k) => k.frame !== action.frame)
        if (kfs.length > 0) curves[action.prop] = kfs
        else delete curves[action.prop]
        return { ...it, keyframes: Object.keys(curves).length ? curves : null }
      })

    case 'clear_keyframes':
      return mapItem(doc, action.itemId, (it) => {
        if (action.prop === undefined) return { ...it, keyframes: null }
        const curves: Record<string, Keyframe[]> = { ...(it.keyframes ?? {}) }
        delete curves[action.prop]
        return { ...it, keyframes: Object.keys(curves).length ? curves : null }
      })

    // ── 标记 ──
    case 'add_marker':
      return mapActive(doc, (tl) => ({ ...tl, markers: [...tl.markers, action.marker] }))

    case 'update_marker': {
      const tl = activeTimeline(doc)
      if (!tl.markers.some((m) => m.id === action.markerId)) return doc
      return mapActive(doc, (t) => ({ ...t, markers: t.markers.map((m) => (m.id === action.markerId ? { ...m, ...action.patch } : m)) }))
    }

    case 'remove_marker': {
      const tl = activeTimeline(doc)
      if (!tl.markers.some((m) => m.id === action.markerId)) return doc
      return mapActive(doc, (t) => ({ ...t, markers: t.markers.filter((m) => m.id !== action.markerId) }))
    }

    // ── 选择 ──
    case 'select':
      return mapActive(doc, (tl) => {
        if (action.mode === 'toggle' || action.mode === 'add') {
          const ids = [...(tl.selectedIds ?? [])]
          if (action.itemId) {
            if (action.mode === 'toggle') {
              const pos = ids.indexOf(action.itemId)
              if (pos >= 0) ids.splice(pos, 1)
              else ids.push(action.itemId)
            } else if (!ids.includes(action.itemId)) {
              ids.push(action.itemId)
            }
          }
          return { ...tl, selectedId: ids[ids.length - 1] ?? null, selectedIds: ids }
        }
        return { ...tl, selectedId: action.itemId, selectedIds: action.itemId ? [action.itemId] : [] }
      })

    case 'select_many':
      return mapActive(doc, (tl) => ({
        ...tl,
        selectedId: action.ids.length ? action.ids[action.ids.length - 1] : null,
        selectedIds: action.ids,
      }))

    case 'select_all':
      return mapActive(doc, (tl) => {
        const ids = tl.items.map((i) => i.id)
        return { ...tl, selectedId: ids.length ? ids[ids.length - 1] : null, selectedIds: ids }
      })

    // ── 素材池 ──
    case 'add_asset':
      return { ...doc, assets: [...doc.assets, action.asset] }

    case 'create_folder':
      return { ...doc, mediaFolders: [...(doc.mediaFolders ?? []), action.folder] }

    case 'move_assets': {
      const idSet = new Set(action.ids)
      return { ...doc, assets: doc.assets.map((a) => (idSet.has(a.id) ? { ...a, folderId: action.folderId ?? null } : a)) }
    }

    case 'remove_asset': {
      if (!doc.assets.some((a) => a.id === action.assetId)) return doc
      return { ...doc, assets: doc.assets.filter((a) => a.id !== action.assetId) }
    }

    // ── 片段属性补充（A-2） ──
    case 'slip_item':
      return mapItem(doc, action.itemId, (it) => ({ ...it, srcInFrame: (it.srcInFrame ?? 0) + action.deltaInFrames }))

    case 'set_background_fill':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        backgroundFill: action.enabled,
        backgroundFillStrength: action.strength !== undefined ? action.strength : it.backgroundFillStrength,
      }))

    case 'replace_media':
      return mapItem(doc, action.itemId, (it) => ({ ...it, src: action.src }))

    case 'relink_item': {
      const patch: Partial<TimelineItem> = {}
      if (action.src !== undefined) patch.src = action.src
      if (action.sourceAssetId !== undefined) patch.sourceAssetId = action.sourceAssetId
      if (action.sourceRevision !== undefined) patch.sourceRevision = action.sourceRevision
      return mapItem(doc, action.itemId, (it) => ({ ...it, ...patch }))
    }

    case 'update_watermark':
      return mapActive(doc, (tl) => {
        const cur: Watermark = tl.watermark ?? { enabled: false, text: '', position: 'br', opacity: 0.7 }
        const updates: Partial<Watermark> = {}
        if (action.enabled !== undefined) updates.enabled = action.enabled
        if (action.text !== undefined) updates.text = action.text
        if (action.position !== undefined) updates.position = action.position
        if (action.opacity !== undefined) updates.opacity = action.opacity
        if (action.fontSize !== undefined) updates.fontSize = action.fontSize
        if (action.color !== undefined) updates.color = action.color
        if (action.margin !== undefined) updates.margin = action.margin
        return { ...tl, watermark: { ...cur, ...updates } }
      })

    case 'set_item_denoise':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        denoisedSrc: action.denoisedSrc,
        denoiseStrength: action.strength !== undefined ? action.strength : it.denoiseStrength,
      }))

    case 'set_reframe_keyframe':
      return mapItem(doc, action.itemId, (it) => {
        const kfs = (it.reframeKeyframes ?? []).filter((k) => k.frame !== action.frame)
        kfs.push({ frame: action.frame, focalPointX: action.focalPointX, focalPointY: action.focalPointY, magnification: action.magnification })
        kfs.sort((a, b) => a.frame - b.frame)
        return { ...it, reframeKeyframes: kfs }
      })

    case 'remove_reframe_keyframe':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        reframeKeyframes: (it.reframeKeyframes ?? []).filter((k) => k.frame !== action.frame),
      }))

    // ── 转写 ──
    case 'set_item_transcript':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        transcript: action.transcript,
        transcriptGenerationId: action.generationId ?? null,
        transcriptStale: false,
      }))

    case 'set_item_variants':
      return mapItem(doc, action.itemId, (it) => ({ ...it, variants: action.variants }))

    case 'toggle_word':
      return mapItem(doc, action.itemId, (it) => {
        const deleted = [...(it.deletedWordIdx ?? [])]
        const pos = deleted.indexOf(action.idx)
        if (pos >= 0) deleted.splice(pos, 1)
        else deleted.push(action.idx)
        deleted.sort((a, b) => a - b)
        return { ...it, deletedWordIdx: deleted }
      })

    case 'delete_words':
      return mapItem(doc, action.itemId, (it) => {
        const merged = Array.from(new Set([...(it.deletedWordIdx ?? []), ...action.idxs])).sort((a, b) => a - b)
        return { ...it, deletedWordIdx: merged }
      })

    case 'clean_script':
      return mapItem(doc, action.itemId, (it) => {
        const deleted = [...(it.deletedWordIdx ?? [])]
        if (action.removeFillers !== false && it.transcript) {
          it.transcript.forEach((w, i) => {
            if (FILLER_WORDS.has(w.text.trim().toLowerCase()) && !deleted.includes(i)) deleted.push(i)
          })
        }
        deleted.sort((a, b) => a - b)
        return {
          ...it,
          deletedWordIdx: deleted,
          silenceFrames: action.silenceFrames !== undefined ? action.silenceFrames : it.silenceFrames,
          cutPadFrames: action.cutPadFrames !== undefined ? action.cutPadFrames : it.cutPadFrames,
        }
      })

    case 'set_gap_cap':
      return mapItem(doc, action.itemId, (it) => {
        const caps: Record<string, number> = { ...(it.gapCapsMs ?? {}) }
        const key = String(action.afterWordIdx)
        if (action.maxMs === null) delete caps[key]
        else caps[key] = action.maxMs
        return { ...it, gapCapsMs: Object.keys(caps).length ? caps : null }
      })

    case 'set_transcript_play_order':
      return mapItem(doc, action.itemId, (it) => ({ ...it, transcriptPlayOrder: action.playOrder }))

    case 'reorder_track_items':
      return mapActive(doc, (tl) => {
        const result = [...tl.items]
        const trackIndices = result.reduce<number[]>((acc, i, idx) => {
          if (i.track === action.track) acc.push(idx)
          return acc
        }, [])
        const trackItems = trackIndices.map((idx) => result[idx])
        const idToItem = new Map(trackItems.map((i) => [i.id, i]))
        const ordered: TimelineItem[] = []
        for (const oid of action.orderedIds) {
          const it = idToItem.get(oid)
          if (it) ordered.push(action.starts && oid in action.starts ? { ...it, startFrame: action.starts[oid] } : it)
        }
        for (const it of trackItems) {
          if (!action.orderedIds.includes(it.id)) ordered.push(it)
        }
        trackIndices.forEach((pos, k) => { result[pos] = ordered[k] })
        return { ...tl, items: result }
      })

    case 'clear_edits':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        deletedWordIdx: [],
        gapCapsMs: null,
        transcriptPlayOrder: null,
        variants: [],
      }))

    case 'fix_transcript_word':
      return mapItem(doc, action.itemId, (it) => {
        const transcript = [...(it.transcript ?? [])]
        if (action.wordIdx < transcript.length) {
          transcript[action.wordIdx] = { ...transcript[action.wordIdx], text: action.text }
        }
        return { ...it, transcript }
      })

    case 'rename_speaker':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        transcript: (it.transcript ?? []).map((w) => (w.speaker === action.fromSpeaker ? { ...w, speaker: action.toSpeaker } : w)),
      }))

    case 'set_asset_transcription': {
      if (!doc.assets.some((a) => a.id === action.assetId)) return doc
      return {
        ...doc,
        assets: doc.assets.map((a) =>
          a.id === action.assetId
            ? {
                ...a,
                transcript: action.transcript,
                transcriptSourceRevision: action.sourceRevision ?? a.transcriptSourceRevision,
                transcriptStale: false,
              }
            : a,
        ),
      }
    }

    // ── 项目级 ──
    case 'create_timeline':
      return {
        ...doc,
        timelines: [...doc.timelines, action.timeline],
        activeTimelineId: action.activate ? action.timeline.id : doc.activeTimelineId,
      }

    case 'switch_timeline':
      return { ...doc, activeTimelineId: action.timelineId }

    case 'duplicate_timeline': {
      const src = doc.timelines.find((t) => t.id === action.timelineId)
      if (!src) return doc
      const maxOrder = doc.timelines.reduce((m, t) => Math.max(m, t.order ?? 0), 0)
      return { ...doc, timelines: [...doc.timelines, { ...src, id: action.newId, name: action.name, order: maxOrder + 1 }] }
    }

    case 'delete_timeline': {
      if (!doc.timelines.some((t) => t.id === action.timelineId)) return doc
      const timelines = doc.timelines.filter((t) => t.id !== action.timelineId)
      let active = doc.activeTimelineId
      if (active === action.timelineId) active = timelines[0]?.id ?? ''
      return { ...doc, timelines, activeTimelineId: active }
    }

    case 'rename_timeline': {
      if (!doc.timelines.some((t) => t.id === action.timelineId)) return doc
      return { ...doc, timelines: doc.timelines.map((t) => (t.id === action.timelineId ? { ...t, name: action.name } : t)) }
    }

    case 'retarget_timeline': {
      if (!doc.timelines.some((t) => t.id === action.timelineId)) return doc
      return {
        ...doc,
        timelines: doc.timelines.map((t) =>
          t.id === action.timelineId ? { ...t, width: action.width, height: action.height, fit: action.fit ?? null } : t,
        ),
      }
    }

    case 'set_timeline_hidden': {
      if (!doc.timelines.some((t) => t.id === action.timelineId)) return doc
      return { ...doc, timelines: doc.timelines.map((t) => (t.id === action.timelineId ? { ...t, hidden: action.hidden } : t)) }
    }

    case 'set_project_doc':
      return action.doc

    case 'rename_folder': {
      if (!(doc.mediaFolders ?? []).some((f) => f.id === action.folderId)) return doc
      return { ...doc, mediaFolders: (doc.mediaFolders ?? []).map((f) => (f.id === action.folderId ? { ...f, name: action.name } : f)) }
    }

    case 'delete_folder': {
      if (!(doc.mediaFolders ?? []).some((f) => f.id === action.folderId)) return doc
      return {
        ...doc,
        mediaFolders: (doc.mediaFolders ?? []).filter((f) => f.id !== action.folderId),
        assets: doc.assets.map((a) => (a.folderId === action.folderId ? { ...a, folderId: null } : a)),
      }
    }

    case 'update_asset': {
      if (!doc.assets.some((a) => a.id === action.assetId)) return doc
      return { ...doc, assets: doc.assets.map((a) => (a.id === action.assetId ? { ...a, ...action.patch } : a)) }
    }

    case 'relink_asset': {
      if (!doc.assets.some((a) => a.id === action.assetId)) return doc
      return { ...doc, assets: doc.assets.map((a) => (a.id === action.assetId ? { ...a, src: action.src } : a)) }
    }

    case 'canonicalize_asset': {
      const rewired = mapActive(doc, (tl) => ({
        ...tl,
        items: tl.items.map((i) => (i.sourceAssetId === action.duplicateId ? { ...i, sourceAssetId: action.canonicalId } : i)),
      }))
      return { ...rewired, assets: rewired.assets.filter((a) => a.id !== action.duplicateId) }
    }

    case 'set_design_style':
      return { ...doc, designStyle: action.style ?? null }

    case 'patch_design_style': {
      const cur = { ...(doc.designStyle ?? {}) }
      Object.assign(cur, action.patch)
      return { ...doc, designStyle: cur }
    }

    case 'set_full_state':
      return mapActive(doc, (tl) => ({ ...tl, ...action.patch }))

    // ── 多机位 ──
    case 'tighten_track':
      return mapActive(doc, (tl) => {
        const trackItems = tl.items.filter((i) => i.track === action.track).sort((a, b) => a.startFrame - b.startFrame)
        const newStart: Record<string, number> = {}
        let cursor = 0
        for (const it of trackItems) {
          newStart[it.id] = cursor
          cursor += it.durationInFrames
        }
        return { ...tl, items: tl.items.map((i) => (i.id in newStart ? { ...i, startFrame: newStart[i.id] } : i)) }
      })

    case 'set_canvas':
      return mapActive(doc, (tl) => ({ ...tl, width: action.width, height: action.height, fit: action.fit ?? null }))

    case 'set_multicam_groups':
      return mapActive(doc, (tl) => ({ ...tl, multicamGroups: action.groups }))

    case 'add_multicam_decision':
      return mapActive(doc, (tl) => {
        const decision: MulticamAngleDecision = {
          id: action.decisionId ?? genId(),
          fromFrame: action.fromFrame,
          toFrame: action.toFrame,
          angleId: action.angleId,
        }
        const groups = (tl.multicamGroups ?? []).map((g) =>
          g.id === action.groupId ? { ...g, decisions: [...(g.decisions ?? []), decision] } : g,
        )
        return { ...tl, multicamGroups: groups }
      })

    case 'set_link_groups':
      return mapActive(doc, (tl) => ({ ...tl, linkGroups: action.groups }))

    case 'add_link_group':
      return mapActive(doc, (tl) => ({ ...tl, linkGroups: [...(tl.linkGroups ?? []), action.group] }))
  }
}

// ── historyReduce（快照栈） ───────────────────────────────────────────────

export interface History {
  past: ProjectDoc[]
  present: ProjectDoc
  future: ProjectDoc[]
}

export const HISTORY_LIMIT = 100

// 非 mutation action：只换 present、不进历史（对齐 design.md 1.3：
// select/switch 是导航/选择，不应被 undo/redo 撤销）。
const NON_MUTATION_TYPES: ReadonlySet<string> = new Set([
  'select', 'select_many', 'select_all', 'switch_timeline',
])

export function initHistory(initial: ProjectDoc): History {
  return { past: [], present: { ...initial, docVersion: Math.max(1, initial.docVersion ?? 1) }, future: [] }
}

export function historyReduce(h: History, action: Action): History {
  if (action.type === 'undo') {
    if (h.past.length === 0) return h
    // 撤销恢复内容快照，但版本不能随历史快照回退；它本身也是一次新的工程变更。
    const restored = { ...h.past[h.past.length - 1], docVersion: h.present.docVersion + 1 }
    return {
      past: h.past.slice(0, -1),
      present: restored,
      future: [h.present, ...h.future],
    }
  }
  if (action.type === 'redo') {
    if (h.future.length === 0) return h
    // redo 与 undo 一样产生新版本，避免 docVersion 在历史栈中来回跳变。
    const restored = { ...h.future[0], docVersion: h.present.docVersion + 1 }
    return {
      past: [...h.past, h.present],
      present: restored,
      future: h.future.slice(1),
    }
  }
  const next = projectReduce(h.present, action)
  if (next === h.present) return h // 无效动作不进历史
  if (NON_MUTATION_TYPES.has(action.type)) {
    // 只换 present，历史/redo 栈不变（选择/导航不产生撤销节点）
    return { ...h, present: next }
  }
  // 普通编辑的版本递增集中在 reducer 历史边界，命令和组件不各自维护计数。
  const versioned = { ...next, docVersion: h.present.docVersion + 1 }
  return {
    past: [...h.past, h.present].slice(-HISTORY_LIMIT),
    present: versioned,
    future: [],
  }
}
