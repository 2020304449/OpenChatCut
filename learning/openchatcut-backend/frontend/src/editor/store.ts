// 编辑器 store：useEditor 持有 History（快照栈）唯一真源，Vue3 ref 落地。

import { computed, ref, type ComputedRef } from 'vue'
import type { Action } from './reduce'
import { HISTORY_LIMIT, historyReduce, initHistory, type History } from './reduce'
import { buildCommands, type EditorCommands } from './commands'
import type { ProjectDoc } from './types'

export interface EditorStore {
  doc: ComputedRef<ProjectDoc>
  commands: EditorCommands
  canUndo: ComputedRef<boolean>
  canRedo: ComputedRef<boolean>
  dispatch: (a: Action) => void
  reset: (doc: ProjectDoc) => void
  /** 把已在 staging 验证通过的 Proposal 文档作为一个撤销组提交。 */
  commitProposal: (doc: ProjectDoc) => void
}

export function useEditor(initial: ProjectDoc): EditorStore {
  const h = ref<History>(initHistory(initial))

  function dispatch(a: Action): void {
    // 所有编辑入口（按钮、快捷键、Agent）都经过同一个历史边界，保证版本和撤销栈同步。
    h.value = historyReduce(h.value, a)
  }

  // 加载外部快照：替换 present 并清空 undo/redo 历史
  function reset(doc: ProjectDoc): void {
    h.value = initHistory(doc)
  }

  /**
   * Proposal 的全部 op 已在 draft 中试运行，这里只做一次历史提交。
   * 无论 Proposal 含多少个 op，用户都只需一次撤销。
   */
  function commitProposal(doc: ProjectDoc): void {
    // Proposal 提交会清空 redo：新分支一旦落地，旧的前进历史就不再适用。
    h.value = {
      past: [...h.value.past, h.value.present].slice(-HISTORY_LIMIT),
      present: { ...doc, docVersion: h.value.present.docVersion + 1 },
      future: [],
    }
  }

  const commands = buildCommands(dispatch)

  return {
    doc: computed(() => h.value.present),
    commands,
    canUndo: computed(() => h.value.past.length > 0),
    canRedo: computed(() => h.value.future.length > 0),
    dispatch,
    reset,
    commitProposal,
  }
}
