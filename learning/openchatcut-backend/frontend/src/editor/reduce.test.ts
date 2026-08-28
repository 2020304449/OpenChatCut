// editor 骨架 reducer 测试（快照栈 + 13 骨架命令 + draft）。
import { describe, expect, it } from 'vitest'
import { buildCommands } from './commands'
import { makeDraft, replayActions } from './draft'
import { historyReduce, initHistory, projectReduce } from './reduce'
import { activeTimeline, defaultProject, type TimelineItem } from './types'

function item(partial: Partial<TimelineItem> & { id: string }): TimelineItem {
  return { track: 'V1', startFrame: 0, durationInFrames: 90, name: '', kind: 'video', ...partial }
}

describe('historyReduce 快照栈', () => {
  it('undo/redo 恢复快照', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1', name: 'A' }) })
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i2', name: 'B' }) })
    expect(activeTimeline(h.present).items.length).toBe(2)

    h = historyReduce(h, { type: 'undo' })
    expect(activeTimeline(h.present).items.length).toBe(1)

    h = historyReduce(h, { type: 'redo' })
    expect(activeTimeline(h.present).items.length).toBe(2)
  })

  it('无效动作不进历史', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'move_item', itemId: '不存在', track: 'V2' })
    expect(h.past.length).toBe(0) // 找不到 item，原 doc 不变
  })
})

describe('骨架命令', () => {
  it('move_item / retime_item', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'move_item', itemId: 'i1', track: 'V2' })
    expect(activeTimeline(h.present).items[0].track).toBe('V2')

    h = historyReduce(h, { type: 'retime_item', itemId: 'i1', durationInFrames: 120, srcInFrame: 10 })
    const it = activeTimeline(h.present).items[0]
    expect(it.durationInFrames).toBe(120)
    expect(it.srcInFrame).toBe(10)
  })

  it('set_item_volume / set_item_transform', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'set_item_volume', itemId: 'i1', volume: 0.5 })
    expect(activeTimeline(h.present).items[0].volume).toBe(0.5)

    h = historyReduce(h, { type: 'set_item_transform', itemId: 'i1', patch: { x: 10, rotation: 45 } })
    const t = activeTimeline(h.present).items[0].transform
    expect(t?.x).toBe(10)
    expect(t?.rotation).toBe(45)
  })

  it('duplicate_item 在源后插入副本', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1', durationInFrames: 90 }) })
    h = historyReduce(h, { type: 'duplicate_item', itemId: 'i1', newId: 'i2' })
    const items = activeTimeline(h.present).items
    expect(items.length).toBe(2)
    expect(items[1].id).toBe('i2')
    expect(items[1].startFrame).toBe(90) // 源 durationInFrames 后移
  })

  it('split_item 越界保持原样', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'a', startFrame: 0, durationInFrames: 100 }) })
    h = historyReduce(h, { type: 'split_item', itemId: 'a', atFrame: 40, newId: 'b' })
    const items = activeTimeline(h.present).items
    expect(items.length).toBe(2)
    expect(items[0].durationInFrames).toBe(40)
    expect(items[1].startFrame).toBe(40)
    expect(items[1].durationInFrames).toBe(60)

    // 越界
    h = historyReduce(h, { type: 'split_item', itemId: 'b', atFrame: 200, newId: 'c' })
    expect(activeTimeline(h.present).items.length).toBe(2) // 未变
  })

  it('remove_item 连坐清除转场', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, {
      type: 'add_transition',
      transition: { id: 'tr1', incomingItemId: 'i1', transType: 'crossfade', durationInFrames: 15 },
    })
    h = historyReduce(h, { type: 'remove_item', itemId: 'i1' })
    expect(activeTimeline(h.present).transitions.length).toBe(0)
  })
})

describe('命令层 + draft', () => {
  it('buildCommands 驱动 reducer', () => {
    let h = initHistory(defaultProject())
    const commands = buildCommands((a) => {
      h = historyReduce(h, a)
    })
    commands.addItem(item({ id: 'i1', name: 'A' }))
    commands.undo()
    expect(activeTimeline(h.present).items.length).toBe(0)
  })

  it('makeDraft 不污染真库，replayActions 应用', () => {
    const base = defaultProject()
    const draft = makeDraft(base)
    draft.commands.addItem(item({ id: 'd1', name: '草稿' }))
    expect(activeTimeline(draft.getDoc()).items.length).toBe(1)
    expect(activeTimeline(base).items.length).toBe(0) // 真库未污染

    const actions = draft.takeActions()
    expect(actions.length).toBe(1)
    const applied = replayActions(base, actions)
    expect(activeTimeline(applied).items.length).toBe(1)
  })
})

describe('projectReduce 纯函数', () => {
  it('不原地修改输入 doc', () => {
    const doc = defaultProject()
    const next = projectReduce(doc, { type: 'add_item', item: item({ id: 'i1' }) })
    expect(activeTimeline(doc).items.length).toBe(0) // 原 doc 不变
    expect(activeTimeline(next).items.length).toBe(1)
  })
})
