// 编辑器 store：useEditor 持有 History（快照栈）唯一真源，Vue3 ref 落地。

import { computed, ref, type ComputedRef } from 'vue'
import type { Action } from './reduce'
import { historyReduce, initHistory, type History } from './reduce'
import { buildCommands, type EditorCommands } from './commands'
import type { ProjectDoc } from './types'

export interface EditorStore {
  doc: ComputedRef<ProjectDoc>
  commands: EditorCommands
  canUndo: ComputedRef<boolean>
  canRedo: ComputedRef<boolean>
  dispatch: (a: Action) => void
  reset: (doc: ProjectDoc) => void
}

export function useEditor(initial: ProjectDoc): EditorStore {
  const h = ref<History>(initHistory(initial))

  function dispatch(a: Action): void {
    h.value = historyReduce(h.value, a)
  }

  // 加载外部快照：替换 present 并清空 undo/redo 历史
  function reset(doc: ProjectDoc): void {
    h.value = initHistory(doc)
  }

  const commands = buildCommands(dispatch)

  return {
    doc: computed(() => h.value.present),
    commands,
    canUndo: computed(() => h.value.past.length > 0),
    canRedo: computed(() => h.value.future.length > 0),
    dispatch,
    reset,
  }
}
