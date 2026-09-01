// 工具执行器（对齐 src/agent/tools.ts）：工具 == 命令（tool == command）。
// executeTool 按工具名把 LLM 传来的参数映射到 EditorCommands → reducer（browser 权威）。
// 只读工具从 getDoc() 读当前状态；编辑工具调用 ctx.commands 派发 action。

import { newId, type EditorCommands } from '../editor/commands'
import {
  activeTimeline,
  type CaptionsData,
  type ClipEffect,
  type MediaAsset,
  type MediaFolder,
  type MulticamGroup,
  type ProjectDoc,
  type Timeline,
  type TimelineItem,
  type TimelineLinkGroup,
  type TransitionItem,
  type TranscriptVariant,
  type TranscriptWord,
} from '../editor/types'

// 工具执行上下文：browser 权威的唯一真源（真库 store 或 edit-session 的 draft）。
export interface ToolContext {
  getDoc(): ProjectDoc
  commands: EditorCommands
}

export type ExecuteTool = (
  name: string,
  args: Record<string, unknown>,
  ctx: ToolContext,
) => Record<string, unknown>

// ── 参数取值 helper ────────────────────────────────────────────────────────

function asStr(v: unknown, fallback = ''): string {
  return typeof v === 'string' ? v : fallback
}
function asNum(v: unknown, fallback = 0): number {
  return typeof v === 'number' ? v : fallback
}
function asBool(v: unknown, fallback = false): boolean {
  return typeof v === 'boolean' ? v : fallback
}
function asDict(v: unknown): Record<string, unknown> {
  return (v && typeof v === 'object' ? v : {}) as Record<string, unknown>
}
function asStrArr(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
}
function asNumArr(v: unknown): number[] {
  return Array.isArray(v) ? v.filter((x): x is number => typeof x === 'number') : []
}

// 目标片段不存在时返回错误 dict（对齐 Python _missing_item）
function missingItem(ctx: ToolContext, itemId: string): Record<string, unknown> | null {
  const tl = activeTimeline(ctx.getDoc())
  if (!tl.items.some((i) => i.id === itemId)) return { ok: false, error: `item not found: ${itemId}` }
  return null
}

// ── 只读工具 ───────────────────────────────────────────────────────────────

function readTimeline(ctx: ToolContext): Record<string, unknown> {
  const tl = activeTimeline(ctx.getDoc())
  return { ok: true, ...tl }
}

function readProject(ctx: ToolContext): Record<string, unknown> {
  const doc = ctx.getDoc()
  return {
    ok: true,
    activeTimelineId: doc.activeTimelineId,
    timelines: doc.timelines.map((t) => ({ id: t.id, name: t.name, items: t.items.length })),
    assetCount: doc.assets.length,
    assets: doc.assets.map((a) => ({
      id: a.id, name: a.name, kind: a.kind, src: a.src,
      durationInFrames: a.durationInFrames, width: a.width, height: a.height,
      favorite: a.favorite, folderId: a.folderId,
    })),
  }
}

function readTranscript(itemId: string, ctx: ToolContext): Record<string, unknown> {
  const tl = activeTimeline(ctx.getDoc())
  const item = tl.items.find((i) => i.id === itemId)
  if (!item) return { ok: false, error: `item not found: ${itemId}` }
  const transcript = (item.transcript ?? []).map((w) => ({ text: w.text, startMs: w.startMs, endMs: w.endMs, speaker: w.speaker }))
  return { ok: true, transcript, deletedWordIdx: item.deletedWordIdx ?? [] }
}

function wordsFrom(v: unknown): TranscriptWord[] {
  if (!Array.isArray(v)) return []
  return v.map((w) => {
    const d = asDict(w)
    return { text: asStr(d.text), startMs: asNum(d.startMs), endMs: asNum(d.endMs), speaker: d.speaker as string | undefined }
  })
}

// ── executeTool ────────────────────────────────────────────────────────────

export function executeTool(name: string, args: Record<string, unknown>, ctx: ToolContext): Record<string, unknown> {
  switch (name) {
    // ── 只读 ──
    case 'read_timeline':
      return readTimeline(ctx)
    case 'read_project':
      return readProject(ctx)
    case 'read_transcript':
      return readTranscript(asStr(args.itemId), ctx)

    // ── 轨道 ──
    case 'edit_track': {
      const action = asStr(args.action)
      const track = asStr(args.track)
      if (action === 'create') {
        if (!asStr(args.kind)) return { ok: false, error: 'create 需要 kind' }
        ctx.commands.createTrack(track, asStr(args.kind), asStr(args.name))
        return { ok: true, track, action: 'create' }
      }
      if (action === 'update') { ctx.commands.updateTrack(track, asDict(args.patch) as never); return { ok: true, track, action: 'update' } }
      if (action === 'delete') { ctx.commands.deleteTrack(track); return { ok: true, track, action: 'delete' } }
      if (action === 'toggle') {
        if (!asStr(args.flag)) return { ok: false, error: 'toggle 需要 flag' }
        ctx.commands.toggleTrackFlag(track, asStr(args.flag), asBool(args.value))
        return { ok: true, track, flag: asStr(args.flag) }
      }
      if (action === 'tighten') { ctx.commands.tightenTrack(track); return { ok: true, track, action: 'tighten' } }
      return { ok: false, error: `unknown action: ${action}` }
    }

    // ── 片段基础 ──
    case 'edit_item': {
      const tl = activeTimeline(ctx.getDoc())
      const doc = ctx.getDoc()
      const appendStart = (track: string): number =>
        tl.items.filter((i) => i.track === track).reduce((m, i) => Math.max(m, i.startFrame + i.durationInFrames), 0)
      const added: Record<string, unknown>[] = []
      const updated: Record<string, unknown>[] = []
      const deleted: Record<string, unknown>[] = []

      // adds：素材池引用 + authored text/solid
      for (const raw of Array.isArray(args.adds) ? args.adds : []) {
        const e = asDict(raw)
        const type = asStr(e.type)
        const track = asStr(e.track) || (type === 'audio' ? 'A1' : 'V1')
        const startFrame = typeof e.fromFrame === 'number' ? e.fromFrame
          : typeof e.startFrame === 'number' ? e.startFrame : appendStart(track)
        let item: TimelineItem
        if (type === 'text' || type === 'solid') {
          const props: Record<string, unknown> = {}
          if (type === 'text') {
            props.text = asStr(e.text, '文字')
            props.color = asStr(e.color, '#ffffff')
            props.align = e.align === 'left' || e.align === 'right' || e.align === 'center' ? e.align : 'center'
            if (typeof e.fontSize === 'number') props.fontSize = e.fontSize
            if (typeof e.fontWeight === 'number') props.fontWeight = e.fontWeight
          } else {
            props.color = asStr(e.color, '#1a1a1a')
          }
          item = {
            id: newId(), track, startFrame,
            durationInFrames: typeof e.durationInFrames === 'number' ? e.durationInFrames : (type === 'text' ? 90 : 150),
            name: asStr(e.name) || (type === 'text' ? '文字' : '纯色'),
            kind: type as TimelineItem['kind'],
            props,
          }
        } else {
          const assetId = asStr(e.assetId)
          const asset = doc.assets.find((a) => a.id === assetId)
          if (!asset) return { ok: false, error: `asset not found: ${assetId}` }
          item = {
            id: newId(), track, startFrame,
            durationInFrames: typeof e.durationInFrames === 'number' ? e.durationInFrames : (asset.durationInFrames ?? 0),
            name: asset.name,
            kind: asset.kind as TimelineItem['kind'],
            src: asset.src ?? null,
            sourceAssetId: asset.id,
            sourceFilename: asset.name,
          }
        }
        ctx.commands.addItem(item)
        added.push({ itemId: item.id, track, startFrame, durationInFrames: item.durationInFrames, kind: item.kind })
      }

      // updates：移动/裁剪/重定时/属性/音量/淡入淡出/变换/滤镜/速率
      for (const raw of Array.isArray(args.updates) ? args.updates : []) {
        const e = asDict(raw)
        const id = asStr(e.itemId) || asStr(e.id)
        const missing = missingItem(ctx, id)
        if (missing) return missing
        const hasField = ['track', 'fromFrame', 'startFrame', 'durationInFrames', 'srcInFrame', 'sourceStartFrame',
          'props', 'volume', 'fadeInSeconds', 'fadeOutSeconds', 'transform', 'filters', 'speed', 'playbackRate']
          .some((k) => e[k] !== undefined)
        if (!hasField) return { ok: false, error: 'update needs at least one field' }
        const sf = typeof e.fromFrame === 'number' ? e.fromFrame : typeof e.startFrame === 'number' ? e.startFrame : undefined
        const srcIn = typeof e.srcInFrame === 'number' ? e.srcInFrame : typeof e.sourceStartFrame === 'number' ? e.sourceStartFrame : undefined
        if (e.track !== undefined || sf !== undefined) ctx.commands.moveItem(id, e.track as string | undefined, sf)
        if (e.durationInFrames !== undefined || srcIn !== undefined) ctx.commands.retimeItem(id, { durationInFrames: e.durationInFrames as number | undefined, srcInFrame: srcIn })
        if (e.props !== undefined) ctx.commands.updateItemProps(id, { props: asDict(e.props) } as never)
        if (typeof e.volume === 'number') ctx.commands.setItemVolume(id, e.volume)
        if (e.fadeInSeconds !== undefined || e.fadeOutSeconds !== undefined) {
          const fps = tl.fps || 30
          ctx.commands.setItemFade(id, {
            fadeInFrames: typeof e.fadeInSeconds === 'number' ? Math.round(e.fadeInSeconds * fps) : undefined,
            fadeOutFrames: typeof e.fadeOutSeconds === 'number' ? Math.round(e.fadeOutSeconds * fps) : undefined,
          })
        }
        if (e.transform !== undefined) ctx.commands.setItemTransform(id, asDict(e.transform) as never)
        if (e.filters !== undefined) ctx.commands.setItemFilters(id, asDict(e.filters) as never)
        const rate = typeof e.speed === 'number' ? e.speed : typeof e.playbackRate === 'number' ? e.playbackRate : undefined
        if (rate !== undefined) ctx.commands.setItemSpeed(id, rate)
        updated.push({ itemId: id })
      }

      // deletes：按 itemId 移除
      for (const raw of Array.isArray(args.deletes) ? args.deletes : []) {
        const e = asDict(raw)
        const id = asStr(e.itemId) || asStr(e.id)
        const missing = missingItem(ctx, id)
        if (missing) return missing
        ctx.commands.removeItem(id)
        deleted.push({ itemId: id })
      }

      return { ok: true, added, updated, deleted }
    }
    case 'remove_item': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.removeItem(id)
      return { ok: true, itemId: id }
    }
    case 'clear_timeline':
      ctx.commands.clearTimeline()
      return { ok: true }
    case 'duplicate_item': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      const nid = newId()
      ctx.commands.duplicateItem(id, nid)
      return { ok: true, itemId: nid }
    }
    case 'split_clip': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      const nid = newId()
      ctx.commands.splitItem(id, asNum(args.atFrame), nid)
      return { ok: true, itemId: nid, atFrame: asNum(args.atFrame) }
    }
    case 'move_item': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.moveItem(id, args.track as string | undefined, args.startFrame as number | undefined)
      return { ok: true, itemId: id }
    }
    case 'set_item_timing': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.retimeItem(id, {
        startFrame: args.startFrame as number | undefined,
        durationInFrames: args.durationInFrames as number | undefined,
        srcInFrame: args.srcInFrame as number | undefined,
      })
      return { ok: true, itemId: id }
    }
    case 'update_item_props': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.updateItemProps(id, asDict(args.patch) as never)
      return { ok: true, itemId: id }
    }

    // ── 片段属性 ──
    case 'set_clip_volume': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setItemVolume(id, asNum(args.volume, 1))
      return { ok: true, itemId: id }
    }
    case 'set_clip_fade': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setItemFade(id, {
        fadeInFrames: args.fadeInFrames as number | undefined,
        fadeOutFrames: args.fadeOutFrames as number | undefined,
      })
      return { ok: true, itemId: id }
    }
    case 'set_clip_transform': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setItemTransform(id, asDict(args.patch) as never)
      return { ok: true, itemId: id }
    }
    case 'set_clip_filters': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setItemFilters(id, asDict(args.patch) as never)
      return { ok: true, itemId: id }
    }
    case 'set_clip_speed': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setItemSpeed(id, asNum(args.rate, 1))
      return { ok: true, itemId: id }
    }
    case 'set_clip_zoom': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setItemZoom(id, asDict(args.patch) as never)
      return { ok: true, itemId: id }
    }
    case 'set_clip_effects': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      const effects: ClipEffect[] = (Array.isArray(args.effects) ? args.effects : []).map((ef) => {
        const d = asDict(ef)
        return { id: asStr(d.id), assetId: asStr(d.assetId), overrides: (d.overrides as Record<string, unknown> | undefined) }
      })
      ctx.commands.setItemEffects(id, effects)
      return { ok: true, itemId: id }
    }

    // ── 转场 ──
    case 'add_transition': {
      const tl = activeTimeline(ctx.getDoc())
      let incoming = asStr(args.incomingItemId)
      if (!incoming || !tl.items.some((i) => i.id === incoming)) incoming = tl.items[tl.items.length - 1]?.id ?? ''
      if (!incoming) return { ok: false, error: '时间线为空，无法加转场' }
      const tr: TransitionItem = {
        id: asStr(args.transitionId) || newId(),
        incomingItemId: incoming,
        transType: asStr(args.transType, 'crossfade'),
        durationInFrames: args.durationInFrames as number | undefined,
      }
      ctx.commands.addTransition(tr)
      return { ok: true, transitionId: tr.id, incomingItemId: incoming }
    }
    case 'edit_transition': {
      const tid = asStr(args.transitionId)
      if (asStr(args.action) === 'update') ctx.commands.setTransition(tid, asDict(args.patch) as never)
      else ctx.commands.removeTransition(tid)
      return { ok: true, transitionId: tid }
    }

    // ── 字幕 ──
    case 'edit_captions': {
      const action = asStr(args.action)
      if (action === 'set') {
        const texts = asStrArr(args.texts)
        const caps: CaptionsData = {
          enabled: (args.enabled as boolean | undefined) !== false,
          items: texts.map((t, i) => ({ startFrame: i * 90, endFrame: (i + 1) * 90, text: t })),
        }
        ctx.commands.setCaptions(caps)
        return { ok: true, count: texts.length }
      }
      if (action === 'update') {
        const patch: Partial<CaptionsData> = {}
        if (typeof args.enabled === 'boolean') patch.enabled = args.enabled
        ctx.commands.updateCaptions(patch)
        return { ok: true }
      }
      if (action === 'set_hidden') {
        ctx.commands.setCaptionsHidden(asBool(args.hidden))
        return { ok: true, hidden: asBool(args.hidden) }
      }
      return { ok: false, error: `unknown action: ${action}` }
    }

    // ── 关键帧 ──
    case 'set_keyframe': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setKeyframe(id, asStr(args.prop), asNum(args.frame), asNum(args.value, 0), args.easing as string | undefined)
      return { ok: true, itemId: id, prop: asStr(args.prop) }
    }
    case 'remove_keyframe': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.removeKeyframe(id, asStr(args.prop), asNum(args.frame))
      return { ok: true, itemId: id }
    }
    case 'clear_keyframes': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.clearKeyframes(id, args.prop as string | undefined)
      return { ok: true, itemId: id }
    }

    // ── 标记 ──
    case 'manage_markers': {
      const action = asStr(args.action)
      if (action === 'add') {
        const m = { id: asStr(args.markerId) || newId(), name: asStr(args.name), frame: args.frame as number | undefined, color: args.color as string | undefined }
        ctx.commands.addMarker(m)
        return { ok: true, markerId: m.id }
      }
      if (action === 'update') { ctx.commands.updateMarker(asStr(args.markerId), asDict(args.patch) as never); return { ok: true, markerId: asStr(args.markerId) } }
      if (action === 'remove') { ctx.commands.removeMarker(asStr(args.markerId)); return { ok: true, markerId: asStr(args.markerId) } }
      return { ok: false, error: `unknown action: ${action}` }
    }

    // ── 选择 ──
    case 'select_clips': {
      const action = asStr(args.action)
      if (action === 'select') ctx.commands.select(args.itemId as string | null, asStr(args.mode, 'replace') as never)
      else if (action === 'select_many') ctx.commands.selectMany(asStrArr(args.ids))
      else ctx.commands.selectAll()
      return { ok: true }
    }

    // ── 素材池 ──
    case 'manage_media_pool': {
      const action = asStr(args.action)
      if (action === 'list') {
        const doc = ctx.getDoc()
        return { ok: true, assets: doc.assets.map((a) => ({ id: a.id, name: a.name, kind: a.kind, src: a.src, durationInFrames: a.durationInFrames, width: a.width, height: a.height, favorite: a.favorite, folderId: a.folderId })), folders: (doc.mediaFolders ?? []).map((f) => ({ id: f.id, name: f.name })) }
      }
      if (action === 'add_asset') {
        const a: MediaAsset = { id: asStr(args.assetId) || newId(), name: asStr(args.name), kind: asStr(args.kind, 'video'), src: asStr(args.src) }
        ctx.commands.addAsset(a)
        return { ok: true, assetId: a.id }
      }
      if (action === 'create_folder') {
        const f: MediaFolder = { id: newId(), name: asStr(args.name) }
        ctx.commands.createFolder(f)
        return { ok: true, folderId: f.id }
      }
      if (action === 'rename_folder') { ctx.commands.renameFolder(asStr(args.folderId), asStr(args.newName) || asStr(args.name)); return { ok: true } }
      if (action === 'delete_folder') { ctx.commands.deleteFolder(asStr(args.folderId)); return { ok: true } }
      if (action === 'move_assets') { ctx.commands.moveAssets(asStrArr(args.ids), args.folderId as string | undefined); return { ok: true } }
      if (action === 'remove_asset') { ctx.commands.removeAsset(asStr(args.assetId)); return { ok: true, assetId: asStr(args.assetId) } }
      if (action === 'rename_asset') { ctx.commands.updateAsset(asStr(args.assetId), { name: asStr(args.newName) || asStr(args.name) }); return { ok: true, assetId: asStr(args.assetId) } }
      if (action === 'favorite_assets' || action === 'unfavorite_assets') {
        const fav = action === 'favorite_assets'
        const ids = asStrArr(args.assetIds).length ? asStrArr(args.assetIds) : (asStr(args.assetId) ? [asStr(args.assetId)] : [])
        for (const id of ids) ctx.commands.updateAsset(id, { favorite: fav })
        return { ok: true }
      }
      if (action === 'relink_asset') { ctx.commands.relinkAsset(asStr(args.assetId), asStr(args.src)); return { ok: true, assetId: asStr(args.assetId) } }
      return { ok: false, error: `unknown action: ${action}` }
    }

    // ── 撤销/重做 ──
    case 'undo_last_change':
      ctx.commands.undo()
      return { ok: true }
    case 'redo_last_change':
      ctx.commands.redo()
      return { ok: true }

    // ── 转写 ──
    case 'set_item_transcript': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      const words = wordsFrom(args.words)
      ctx.commands.setItemTranscript(id, words, args.generationId as string | undefined)
      return { ok: true, itemId: id, count: words.length }
    }
    case 'clean_script': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.cleanScript(id, {
        removeFillers: asBool(args.removeFillers, true),
        silenceFrames: args.silenceFrames as number | undefined,
        cutPadFrames: args.cutPadFrames as number | undefined,
      })
      return { ok: true, itemId: id }
    }
    case 'delete_text': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.deleteWords(id, asNumArr(args.wordIndices))
      return { ok: true, itemId: id }
    }
    case 'manage_transcript': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      const action = asStr(args.action)
      if (action === 'fix_word') { ctx.commands.fixTranscriptWord(id, asNum(args.wordIndex), asStr(args.text)); return { ok: true, itemId: id } }
      if (action === 'rename_speaker') { ctx.commands.renameSpeaker(id, asStr(args.fromSpeaker), asStr(args.toSpeaker)); return { ok: true, itemId: id } }
      if (action === 'set_variants') {
        const variants: TranscriptVariant[] = (Array.isArray(args.variants) ? args.variants : []).map((v) => {
          const d = asDict(v)
          const words = (Array.isArray(d.words) ? d.words : []).map((w) => {
            const wd = asDict(w)
            return { i: asNum(wd.i), text: asStr(wd.text) }
          })
          return { id: asStr(d.id) || newId(), lang: asStr(d.lang), kind: asStr(d.kind, 'translation'), label: asStr(d.label), words }
        })
        ctx.commands.setItemVariants(id, variants)
        return { ok: true, itemId: id }
      }
      return { ok: false, error: `unknown action: ${action}` }
    }

    // ── 片段属性补充 ──
    case 'slip_item': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.slipItem(id, asNum(args.deltaInFrames))
      return { ok: true, itemId: id }
    }
    case 'set_background_fill': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setBackgroundFill(id, asBool(args.enabled), args.strength as number | undefined)
      return { ok: true, itemId: id }
    }
    case 'replace_media': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.replaceMedia(id, asStr(args.src))
      return { ok: true, itemId: id }
    }
    case 'update_watermark':
      ctx.commands.updateWatermark({
        enabled: args.enabled as boolean | undefined,
        text: args.text as string | undefined,
        position: args.position as string | undefined,
        opacity: args.opacity as number | undefined,
      })
      return { ok: true }
    case 'set_item_denoise': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setItemDenoise(id, (args.denoisedSrc as string | null) ?? null, args.strength as number | undefined)
      return { ok: true, itemId: id }
    }
    case 'set_reframe_keyframe': {
      const id = asStr(args.itemId)
      const e = missingItem(ctx, id)
      if (e) return e
      ctx.commands.setReframeKeyframe(id, asNum(args.frame), asNum(args.focalPointX), asNum(args.focalPointY), asNum(args.magnification))
      return { ok: true, itemId: id }
    }

    // ── 项目级 ──
    case 'manage_timelines': {
      const action = asStr(args.action)
      if (action === 'create') {
        const tl: Timeline = { id: newId(), name: asStr(args.name, '新时间线'), order: ctx.getDoc().timelines.length, fps: 30, items: [], transitions: [], markers: [], captions: null }
        ctx.commands.createTimeline(tl, false)
        return { ok: true, timelineId: tl.id }
      }
      if (action === 'switch') { ctx.commands.switchTimeline(asStr(args.timelineId)); return { ok: true, timelineId: asStr(args.timelineId) } }
      if (action === 'duplicate') { const nid = newId(); ctx.commands.duplicateTimeline(asStr(args.timelineId), nid, asStr(args.name, '副本')); return { ok: true, timelineId: nid } }
      if (action === 'delete') { ctx.commands.deleteTimeline(asStr(args.timelineId)); return { ok: true, timelineId: asStr(args.timelineId) } }
      if (action === 'rename') { ctx.commands.renameTimeline(asStr(args.timelineId), asStr(args.name)); return { ok: true, timelineId: asStr(args.timelineId) } }
      if (action === 'retarget') { ctx.commands.retargetTimeline(asStr(args.timelineId), asNum(args.width, 1920), asNum(args.height, 1080)); return { ok: true, timelineId: asStr(args.timelineId) } }
      if (action === 'set_hidden') { ctx.commands.setTimelineHidden(asStr(args.timelineId), asBool(args.hidden)); return { ok: true, timelineId: asStr(args.timelineId) } }
      return { ok: false, error: `unknown action: ${action}` }
    }
    case 'edit_asset': {
      const action = asStr(args.action)
      const assetId = asStr(args.assetId)
      if (action === 'update') {
        const patch: Record<string, unknown> = { ...asDict(args.patch) }
        if (args.name !== undefined) patch.name = asStr(args.name)
        if (args.favorite !== undefined) patch.favorite = asBool(args.favorite)
        if (Object.keys(patch).length === 0) return { ok: false, error: 'update 需要 name/favorite/patch 至少一项' }
        ctx.commands.updateAsset(assetId, patch as never)
        return { ok: true, assetId }
      }
      if (action === 'delete') { ctx.commands.removeAsset(assetId); return { ok: true, assetId } }
      return { ok: false, error: `unknown action: ${action}` }
    }
    case 'list_audio': {
      const doc = ctx.getDoc()
      const audios = doc.assets.filter((a) => a.kind === 'audio')
      return { ok: true, audio: audios.map((a) => ({ id: a.id, name: a.name, kind: a.kind, src: a.src, durationInFrames: a.durationInFrames, width: a.width, height: a.height, favorite: a.favorite, folderId: a.folderId })) }
    }
    case 'add_audio': {
      const doc = ctx.getDoc()
      let asset: MediaAsset | undefined
      if (asStr(args.assetId)) {
        asset = doc.assets.find((a) => a.id === asStr(args.assetId) && a.kind === 'audio')
        if (!asset) return { ok: false, error: `audio asset not found: ${asStr(args.assetId)}` }
      } else if (asStr(args.name)) {
        const q = asStr(args.name).toLowerCase()
        const matches = doc.assets.filter((a) => a.kind === 'audio' && a.name.toLowerCase().includes(q))
        if (!matches.length) return { ok: false, error: `no audio asset matching: ${asStr(args.name)}` }
        asset = matches[0]
      } else {
        return { ok: false, error: '需要 name 或 assetId' }
      }
      const track = asStr(args.track, 'A1')
      const tl = activeTimeline(doc)
      const startFrame = typeof args.startFrame === 'number' ? args.startFrame
        : tl.items.filter((i) => i.track === track).reduce((m, i) => Math.max(m, i.startFrame + i.durationInFrames), 0)
      const durationInFrames = typeof args.durationInFrames === 'number' ? args.durationInFrames : (asset.durationInFrames ?? 0)
      const item: TimelineItem = {
        id: newId(), track, startFrame, durationInFrames,
        name: asset.name, kind: 'audio', src: asset.src ?? null,
        sourceAssetId: asset.id, sourceFilename: asset.name,
      }
      ctx.commands.addItem(item)
      return { ok: true, itemId: item.id, track, startFrame, durationInFrames }
    }
    case 'set_design_style': {
      if (asStr(args.action) === 'set') ctx.commands.setDesignStyle((args.style as Record<string, unknown> | null) ?? null)
      else ctx.commands.patchDesignStyle(asDict(args.patch))
      return { ok: true }
    }
    case 'set_full_state':
      ctx.commands.setFullState(asDict(args.patch) as never)
      return { ok: true }

    // ── 多机位 ──
    case 'set_aspect_ratio':
      ctx.commands.setCanvas(asNum(args.width), asNum(args.height), args.fit as string | undefined)
      return { ok: true, width: asNum(args.width), height: asNum(args.height) }
    case 'change_cam': {
      const action = asStr(args.action)
      if (action === 'set_groups') {
        const groups: MulticamGroup[] = (Array.isArray(args.groups) ? args.groups : []).map((g) => {
          const d = asDict(g)
          return {
            id: asStr(d.id) || newId(),
            referenceAngleId: asStr(d.referenceAngleId),
            masterAngleId: asStr(d.masterAngleId),
            angles: (Array.isArray(d.angles) ? d.angles : []).map((a) => {
              const ad = asDict(a)
              return { id: asStr(ad.id) || newId(), itemId: asStr(ad.itemId), label: asStr(ad.label), offsetFrames: asNum(ad.offsetFrames), confidence: asNum(ad.confidence, 1) }
            }),
            syncMethod: asStr(d.syncMethod, 'source-timecode'),
          }
        })
        ctx.commands.setMulticamGroups(groups)
        return { ok: true, count: groups.length }
      }
      if (action === 'add_decision') { ctx.commands.addMulticamDecision(asStr(args.groupId), asNum(args.fromFrame), asNum(args.toFrame), asStr(args.angleId)); return { ok: true } }
      return { ok: false, error: `unknown action: ${action}` }
    }
    case 'manage_link_group': {
      const action = asStr(args.action)
      if (action === 'add') {
        const d = asDict(args.group)
        const grp: TimelineLinkGroup = { id: asStr(d.id) || newId(), itemIds: asStrArr(d.itemIds), anchorItemId: asStr(d.anchorItemId), mode: asStr(d.mode, 'linked') }
        ctx.commands.addLinkGroup(grp)
        return { ok: true, groupId: grp.id }
      }
      if (action === 'set') {
        const groups: TimelineLinkGroup[] = (Array.isArray(args.groups) ? args.groups : []).map((g) => {
          const d = asDict(g)
          return { id: asStr(d.id) || newId(), itemIds: asStrArr(d.itemIds), anchorItemId: asStr(d.anchorItemId), mode: asStr(d.mode, 'linked') }
        })
        ctx.commands.setLinkGroups(groups)
        return { ok: true, count: groups.length }
      }
      return { ok: false, error: `unknown action: ${action}` }
    }

    // TODO(生成/导出类工具)：transcribe_track / probe_media / submit_* 等 20 个是
    // server 端重插件（mock 存根），不经 browser 权威，由 generation_tools.py 直接处理。
    default:
      return { ok: false, error: `tool not implemented: ${name}` }
  }
}

// executeTool 实现覆盖的工具名清单（3 只读 + 44 编辑）。
// 20 个生成/导出类工具（submit_*/transcribe_track/probe_media/...）走 server 端，不在其中。
// 工具清单一致性校验的「前端单源」：新增编辑工具需同时改后端 TOOLS + 本清单 + executeTool case，
// 漏同步会被 tools.test.ts 的一致性测试抓住。
export const SUPPORTED_TOOL_NAMES: readonly string[] = [
  // 只读
  'read_timeline',
  'read_project',
  'read_transcript',
  // 轨道
  'edit_track',
  // 片段基础
  'edit_item',
  'remove_item',
  'clear_timeline',
  'duplicate_item',
  'split_clip',
  'move_item',
  'set_item_timing',
  'update_item_props',
  // 片段属性
  'set_clip_volume',
  'set_clip_fade',
  'set_clip_transform',
  'set_clip_filters',
  'set_clip_speed',
  'set_clip_zoom',
  'set_clip_effects',
  // 转场
  'add_transition',
  'edit_transition',
  // 字幕
  'edit_captions',
  // 关键帧
  'set_keyframe',
  'remove_keyframe',
  'clear_keyframes',
  // 标记
  'manage_markers',
  // 选择
  'select_clips',
  // 素材池
  'manage_media_pool',
  'list_audio',
  'add_audio',
  // 撤销/重做
  'undo_last_change',
  'redo_last_change',
  // 转写
  'set_item_transcript',
  'clean_script',
  'delete_text',
  'manage_transcript',
  // 片段属性补充
  'slip_item',
  'set_background_fill',
  'replace_media',
  'update_watermark',
  'set_item_denoise',
  'set_reframe_keyframe',
  // 项目级
  'manage_timelines',
  'edit_asset',
  'set_design_style',
  'set_full_state',
  // 多机位
  'set_aspect_ratio',
  'change_cam',
  'manage_link_group',
]
