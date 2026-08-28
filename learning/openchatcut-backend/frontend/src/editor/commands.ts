// 命令层：buildCommands 把命令映射为 action（对齐 Python storeCommandBuilder + tool==command）。

import type { Action } from './reduce'
import type { ClipTransform, TimelineItem, TransitionItem } from './types'

export interface EditorCommands {
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
}

export function buildCommands(dispatch: (a: Action) => void): EditorCommands {
  return {
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
  }
}

export function newId(): string {
  return crypto.randomUUID().slice(0, 8)
}
