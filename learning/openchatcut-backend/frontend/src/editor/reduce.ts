// 编辑器 reducer（对齐 Python commands/actions.py + commands/base.py）。

import type { ClipTransform, ProjectDoc, TimelineItem, TransitionItem } from './types'
import { activeTimeline } from './types'

// ── action 类型（骨架命令） ───────────────────────────────────────────────

export type EditAction =
  | { type: 'add_item'; item: TimelineItem }
  | { type: 'remove_item'; itemId: string }
  | { type: 'clear_timeline' }
  | { type: 'duplicate_item'; itemId: string; newId: string }
  | { type: 'split_item'; itemId: string; atFrame: number; newId: string }
  | { type: 'move_item'; itemId: string; track?: string; startFrame?: number }
  | { type: 'retime_item'; itemId: string; startFrame?: number; durationInFrames?: number; srcInFrame?: number }
  | { type: 'set_item_volume'; itemId: string; volume: number }
  | { type: 'set_item_transform'; itemId: string; patch: Partial<ClipTransform> }
  | { type: 'add_transition'; transition: TransitionItem }

export type Action = EditAction | { type: 'undo' } | { type: 'redo' }

// ── 作用域路由 helper（对齐 _map_active / _map_item） ─────────────────────

function mapActive(doc: ProjectDoc, fn: (tl: ProjectDoc['timelines'][number]) => ProjectDoc['timelines'][number]): ProjectDoc {
  const tl = activeTimeline(doc)
  return { ...doc, timelines: doc.timelines.map((t) => (t.id === tl.id ? fn(t) : t)) }
}

function mapItem(doc: ProjectDoc, itemId: string, fn: (it: TimelineItem) => TimelineItem): ProjectDoc {
  const tl = activeTimeline(doc)
  if (!tl.items.some((i) => i.id === itemId)) return doc // 找不到 → 原 doc（无效动作不进历史）
  return mapActive(doc, (t) => ({ ...t, items: t.items.map((i) => (i.id === itemId ? fn(i) : i)) }))
}

// ── projectReduce（纯函数，无副作用） ─────────────────────────────────────

export function projectReduce(doc: ProjectDoc, action: EditAction): ProjectDoc {
  switch (action.type) {
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
      return mapActive(doc, (tl) => ({ ...tl, items: [], transitions: [] }))

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

    case 'set_item_volume':
      return mapItem(doc, action.itemId, (it) => ({ ...it, volume: action.volume }))

    case 'set_item_transform':
      return mapItem(doc, action.itemId, (it) => ({
        ...it,
        transform: { ...(it.transform ?? {}), ...action.patch },
      }))

    case 'add_transition':
      return mapActive(doc, (tl) => ({ ...tl, transitions: [...tl.transitions, action.transition] }))
  }
}

// ── historyReduce（快照栈） ───────────────────────────────────────────────

export interface History {
  past: ProjectDoc[]
  present: ProjectDoc
  future: ProjectDoc[]
}

export const HISTORY_LIMIT = 100

export function initHistory(initial: ProjectDoc): History {
  return { past: [], present: initial, future: [] }
}

export function historyReduce(h: History, action: Action): History {
  if (action.type === 'undo') {
    if (h.past.length === 0) return h
    return {
      past: h.past.slice(0, -1),
      present: h.past[h.past.length - 1],
      future: [h.present, ...h.future],
    }
  }
  if (action.type === 'redo') {
    if (h.future.length === 0) return h
    return {
      past: [...h.past, h.present],
      present: h.future[0],
      future: h.future.slice(1),
    }
  }
  const next = projectReduce(h.present, action)
  if (next === h.present) return h // 无效动作不进历史
  return {
    past: [...h.past, h.present].slice(-HISTORY_LIMIT),
    present: next,
    future: [],
  }
}
