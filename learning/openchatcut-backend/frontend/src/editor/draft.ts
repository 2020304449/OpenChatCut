// 草稿引擎：makeDraft 复用 projectReduce 操作草稿副本，记录 actions（对齐 store.ts 的 makeDraft）。

import type { Action, EditAction } from './reduce'
import { projectReduce } from './reduce'
import { buildCommands, type EditorCommands } from './commands'
import type { ProjectDoc } from './types'

export interface DraftEngine {
  commands: EditorCommands
  getDoc(): ProjectDoc
  takeActions(): EditAction[]
}

export function makeDraft(base: ProjectDoc): DraftEngine {
  let doc = base
  let pending: EditAction[] = []

  const dispatch = (a: Action): void => {
    if (a.type === 'undo' || a.type === 'redo') return // 草稿里历史控制无意义
    const next = projectReduce(doc, a)
    if (next !== doc) {
      doc = next
      pending.push(a)
    }
  }

  return {
    commands: buildCommands(dispatch),
    getDoc: () => doc,
    takeActions: () => {
      const out = pending
      pending = []
      return out
    },
  }
}

export function replayActions(base: ProjectDoc, actions: EditAction[]): ProjectDoc {
  return actions.reduce((d, a) => projectReduce(d, a), base)
}
