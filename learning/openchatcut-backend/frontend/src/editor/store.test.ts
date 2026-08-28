// useEditor.reset：加载外部快照应替换 doc 并清空 undo/redo 历史。
import { describe, expect, it } from 'vitest'
import { useEditor } from './store'
import { defaultProject, type TimelineItem } from './types'

function item(partial: Partial<TimelineItem> & { id: string }): TimelineItem {
  return { track: 'V1', startFrame: 0, durationInFrames: 90, name: '', kind: 'video', ...partial }
}

describe('useEditor.reset', () => {
  it('reset 替换 doc 并清空 undo/redo 历史', () => {
    const store = useEditor(defaultProject())
    store.commands.addItem(item({ id: 'i1', name: 'A' }))
    expect(store.canUndo.value).toBe(true)

    const next = defaultProject()
    store.reset(next)

    expect(store.doc.value).toStrictEqual(next)
    expect(store.canUndo.value).toBe(false)
    expect(store.canRedo.value).toBe(false)
  })
})
