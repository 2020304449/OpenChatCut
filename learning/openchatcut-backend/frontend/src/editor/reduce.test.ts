// editor 骨架 reducer 测试（快照栈 + 13 骨架命令 + draft + 70 低频命令）。
import { describe, expect, it } from 'vitest'
import { buildCommands } from './commands'
import { makeDraft, replayActions } from './draft'
import { historyReduce, initHistory, projectReduce } from './reduce'
import { activeTimeline, defaultProject, type MulticamGroup, type Timeline, type TimelineItem, type TimelineLinkGroup, type TranscriptWord } from './types'

function item(partial: Partial<TimelineItem> & { id: string }): TimelineItem {
  return { track: 'V1', startFrame: 0, durationInFrames: 90, name: '', kind: 'video', ...partial }
}

function timeline(id: string, name: string): Timeline {
  return { id, name, fps: 30, items: [], transitions: [], markers: [], captions: null }
}

const transcript: TranscriptWord[] = [
  { text: '那个', startMs: 0, endMs: 100 },
  { text: 'hello', startMs: 100, endMs: 200 },
  { text: 'world', startMs: 200, endMs: 300, speaker: 'A' },
]

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

  it('select/switch 非 mutation action 不进历史', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i2' }) })
    expect(h.past.length).toBe(2)

    // select / switch 只换 present，不产生撤销节点
    h = historyReduce(h, { type: 'select', itemId: 'i1' })
    h = historyReduce(h, { type: 'select_many', ids: ['i1', 'i2'] })
    h = historyReduce(h, { type: 'switch_timeline', timelineId: 'tl1' })
    expect(h.past.length).toBe(2) // 仍只有两个 add_item
    expect(activeTimeline(h.present).selectedId).toBe('i2')
    expect(h.present.activeTimelineId).toBe('tl1')

    // undo 应回退 add_item，而不是选择/切换
    h = historyReduce(h, { type: 'undo' })
    expect(activeTimeline(h.present).items.length).toBe(1)
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

    const doc2 = defaultProject()
    projectReduce(doc2, { type: 'add_asset', asset: { id: 'a1', name: 'c.mp4', kind: 'video' } })
    expect(doc2.assets.length).toBe(0) // 顶层也未被修改
  })
})

describe('track 命令', () => {
  it('create_track / update_track / toggle_track_flag', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'create_track', trackId: 'V3', kind: 'video', name: '主轨', order: 0 })
    let tl = activeTimeline(h.present)
    expect(tl.tracks?.['V3']).toEqual({ kind: 'video', name: '主轨' })
    expect(tl.trackOrder?.[0]).toBe('V3') // 插入在 order 0

    h = historyReduce(h, { type: 'update_track', trackId: 'V3', patch: { locked: true } })
    tl = activeTimeline(h.present)
    expect(tl.tracks?.['V3']?.locked).toBe(true)

    h = historyReduce(h, { type: 'toggle_track_flag', trackId: 'V3', flag: 'muted', value: true })
    tl = activeTimeline(h.present)
    expect(tl.tracks?.['V3']?.muted).toBe(true)
  })

  it('delete_track 删除条目、轨道顺序与 items', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'create_track', trackId: 'V3', kind: 'video' })
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1', track: 'V3' }) })
    h = historyReduce(h, { type: 'delete_track', trackId: 'V3' })
    const tl = activeTimeline(h.present)
    expect(tl.tracks?.['V3']).toBeUndefined()
    expect(tl.trackOrder?.includes('V3')).toBe(false)
    expect(tl.items.find((i) => i.id === 'i1')).toBeUndefined()
  })
})

describe('片段属性 fade/filters/speed/zoom/effects', () => {
  it('set_item_fade / set_item_filters / set_item_speed / set_item_zoom / set_item_effects', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })

    h = historyReduce(h, { type: 'set_item_fade', itemId: 'i1', fadeInFrames: 15, fadeOutFrames: 30 })
    let it = activeTimeline(h.present).items[0]
    expect(it.fadeInFrames).toBe(15)
    expect(it.fadeOutFrames).toBe(30)

    h = historyReduce(h, { type: 'set_item_filters', itemId: 'i1', patch: { brightness: 1.2, blur: 2 } })
    it = activeTimeline(h.present).items[0]
    expect(it.filters?.brightness).toBe(1.2)
    expect(it.filters?.blur).toBe(2)

    h = historyReduce(h, { type: 'set_item_speed', itemId: 'i1', rate: 2 })
    it = activeTimeline(h.present).items[0]
    expect(it.playbackRate).toBe(2)

    h = historyReduce(h, { type: 'set_item_zoom', itemId: 'i1', patch: { magnification: 1.5 } })
    it = activeTimeline(h.present).items[0]
    expect(it.zoom?.magnification).toBe(1.5)

    h = historyReduce(h, { type: 'set_item_effects', itemId: 'i1', effects: [{ id: 'e1', assetId: 'a1' }] })
    it = activeTimeline(h.present).items[0]
    expect(it.effects?.length).toBe(1)
  })

  it('update_item_props 通用 patch', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'update_item_props', itemId: 'i1', patch: { name: '改名', backgroundFill: true } })
    const it = activeTimeline(h.present).items[0]
    expect(it.name).toBe('改名')
    expect(it.backgroundFill).toBe(true)
  })

  it('无效 id 返回原 doc 不进历史', () => {
    let h = initHistory(defaultProject())
    const before = h
    h = historyReduce(h, { type: 'set_item_filters', itemId: '不存在', patch: { brightness: 1 } })
    expect(h).toBe(before)
  })
})

describe('转场 set_transition/remove_transition', () => {
  it('patch 与删除', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, {
      type: 'add_transition',
      transition: { id: 'tr1', incomingItemId: 'i1', transType: 'crossfade', durationInFrames: 15 },
    })
    h = historyReduce(h, { type: 'set_transition', transitionId: 'tr1', patch: { durationInFrames: 30 } })
    let tl = activeTimeline(h.present)
    expect(tl.transitions[0].durationInFrames).toBe(30)

    h = historyReduce(h, { type: 'remove_transition', transitionId: 'tr1' })
    tl = activeTimeline(h.present)
    expect(tl.transitions.length).toBe(0)

    // 无效 id
    const before = h
    h = historyReduce(h, { type: 'set_transition', transitionId: '不存在', patch: { durationInFrames: 1 } })
    expect(h).toBe(before)
  })
})

describe('字幕 set_captions/update_captions/set_captions_hidden', () => {
  it('字幕闭环', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'set_captions', captions: { enabled: true, items: [{ startFrame: 0, endFrame: 30, text: 'hi' }] } })
    let tl = activeTimeline(h.present)
    expect(tl.captions?.items.length).toBe(1)

    h = historyReduce(h, { type: 'update_captions', patch: { enabled: false } })
    tl = activeTimeline(h.present)
    expect(tl.captions?.enabled).toBe(false)

    h = historyReduce(h, { type: 'set_captions_hidden', hidden: true })
    tl = activeTimeline(h.present)
    expect(tl.captionsHidden).toBe(true)
  })
})

describe('关键帧 set_keyframe/remove_keyframe/clear_keyframes', () => {
  it('set_keyframe 按 frame 排序去重', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'set_keyframe', itemId: 'i1', prop: 'scale', frame: 30, value: 1.2 })
    h = historyReduce(h, { type: 'set_keyframe', itemId: 'i1', prop: 'scale', frame: 10, value: 0.9 })
    const it = activeTimeline(h.present).items[0]
    expect(it.keyframes?.['scale']?.map((k) => k.frame)).toEqual([10, 30])
  })

  it('remove_keyframe / clear_keyframes(prop) / clear_keyframes(全部)', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'set_keyframe', itemId: 'i1', prop: 'x', frame: 0, value: 1 })
    h = historyReduce(h, { type: 'set_keyframe', itemId: 'i1', prop: 'x', frame: 10, value: 2 })
    h = historyReduce(h, { type: 'remove_keyframe', itemId: 'i1', prop: 'x', frame: 0 })
    let it = activeTimeline(h.present).items[0]
    expect(it.keyframes?.['x']?.map((k) => k.frame)).toEqual([10])

    h = historyReduce(h, { type: 'clear_keyframes', itemId: 'i1', prop: 'x' })
    it = activeTimeline(h.present).items[0]
    expect(it.keyframes).toBeNull()

    h = historyReduce(h, { type: 'set_keyframe', itemId: 'i1', prop: 'opacity', frame: 0, value: 1 })
    h = historyReduce(h, { type: 'clear_keyframes', itemId: 'i1' })
    it = activeTimeline(h.present).items[0]
    expect(it.keyframes).toBeNull()
  })
})

describe('标记 add_marker/update_marker/remove_marker', () => {
  it('add/update/remove marker', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_marker', marker: { id: 'm1', name: 'm', frame: 10 } })
    h = historyReduce(h, { type: 'update_marker', markerId: 'm1', patch: { name: 'renamed', color: 'red' } })
    let tl = activeTimeline(h.present)
    expect(tl.markers[0].name).toBe('renamed')
    expect(tl.markers[0].color).toBe('red')

    h = historyReduce(h, { type: 'remove_marker', markerId: 'm1' })
    tl = activeTimeline(h.present)
    expect(tl.markers.length).toBe(0)

    // 无效 id
    const before = h
    h = historyReduce(h, { type: 'update_marker', markerId: '不存在', patch: { name: 'x' } })
    expect(h).toBe(before)
  })
})

describe('选择 select/select_many/select_all', () => {
  it('replace/toggle/add & select_all', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i2' }) })
    h = historyReduce(h, { type: 'select', itemId: 'i1' })
    let tl = activeTimeline(h.present)
    expect(tl.selectedId).toBe('i1')
    expect(tl.selectedIds).toEqual(['i1'])

    h = historyReduce(h, { type: 'select', itemId: 'i2', mode: 'add' })
    tl = activeTimeline(h.present)
    expect(tl.selectedIds).toEqual(['i1', 'i2'])

    h = historyReduce(h, { type: 'select', itemId: 'i1', mode: 'toggle' })
    tl = activeTimeline(h.present)
    expect(tl.selectedIds).toEqual(['i2'])

    h = historyReduce(h, { type: 'select_all' })
    tl = activeTimeline(h.present)
    expect(tl.selectedIds).toEqual(['i1', 'i2'])
  })

  it('select_many', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'a' }) })
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'b' }) })
    h = historyReduce(h, { type: 'select_many', ids: ['a', 'b'] })
    const tl = activeTimeline(h.present)
    expect(tl.selectedIds).toEqual(['a', 'b'])
    expect(tl.selectedId).toBe('b')
  })
})

describe('素材池 add_asset/create_folder/move_assets/remove_asset', () => {
  it('素材池闭环', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_asset', asset: { id: 'a1', name: 'clip.mp4', kind: 'video' } })
    h = historyReduce(h, { type: 'create_folder', folder: { id: 'f1', name: '素材' } })
    h = historyReduce(h, { type: 'move_assets', ids: ['a1'], folderId: 'f1' })
    let doc = h.present
    expect(doc.assets[0].folderId).toBe('f1')
    expect(doc.mediaFolders?.length).toBe(1)

    h = historyReduce(h, { type: 'remove_asset', assetId: 'a1' })
    doc = h.present
    expect(doc.assets.length).toBe(0)

    // 无效 id 返回原 doc
    const before = h
    h = historyReduce(h, { type: 'remove_asset', assetId: '不存在' })
    expect(h).toBe(before)
  })
})

describe('片段属性补充 slip/backgroundFill/relink/watermark/denoise/reframe', () => {
  it('slip_item / set_background_fill / replace_media / relink_item', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1', srcInFrame: 10 }) })
    h = historyReduce(h, { type: 'slip_item', itemId: 'i1', deltaInFrames: 5 })
    let it = activeTimeline(h.present).items[0]
    expect(it.srcInFrame).toBe(15)

    h = historyReduce(h, { type: 'set_background_fill', itemId: 'i1', enabled: true, strength: 70 })
    it = activeTimeline(h.present).items[0]
    expect(it.backgroundFill).toBe(true)
    expect(it.backgroundFillStrength).toBe(70)

    h = historyReduce(h, { type: 'replace_media', itemId: 'i1', src: 'new.mp4' })
    it = activeTimeline(h.present).items[0]
    expect(it.src).toBe('new.mp4')

    h = historyReduce(h, { type: 'relink_item', itemId: 'i1', sourceAssetId: 'a9', sourceRevision: 'r1' })
    it = activeTimeline(h.present).items[0]
    expect(it.sourceAssetId).toBe('a9')
    expect(it.sourceRevision).toBe('r1')

    // 无效 id
    const before = h
    h = historyReduce(h, { type: 'relink_item', itemId: '不存在', src: 'x.mp4' })
    expect(h).toBe(before)
  })

  it('set_item_denoise / update_watermark / reframe', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'update_watermark', text: 'LOGO', enabled: true, opacity: 0.5 })
    let tl = activeTimeline(h.present)
    expect(tl.watermark?.text).toBe('LOGO')
    expect(tl.watermark?.enabled).toBe(true)

    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'set_item_denoise', itemId: 'i1', denoisedSrc: 'n.mp4', strength: 80 })
    let it = activeTimeline(h.present).items[0]
    expect(it.denoisedSrc).toBe('n.mp4')
    expect(it.denoiseStrength).toBe(80)

    h = historyReduce(h, { type: 'set_reframe_keyframe', itemId: 'i1', frame: 0, focalPointX: 0.5, focalPointY: 0.5, magnification: 2 })
    h = historyReduce(h, { type: 'set_reframe_keyframe', itemId: 'i1', frame: 30, focalPointX: 0.6, focalPointY: 0.7, magnification: 1.5 })
    it = activeTimeline(h.present).items[0]
    expect(it.reframeKeyframes?.length).toBe(2)
    expect(it.reframeKeyframes?.[0].frame).toBe(0)

    h = historyReduce(h, { type: 'remove_reframe_keyframe', itemId: 'i1', frame: 0 })
    it = activeTimeline(h.present).items[0]
    expect(it.reframeKeyframes?.length).toBe(1)
  })
})

describe('转写 toggle_word/delete_words/clean_script/fix_word/rename_speaker', () => {
  it('toggle_word / delete_words / set_item_variants', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'toggle_word', itemId: 'i1', idx: 1 })
    let it = activeTimeline(h.present).items[0]
    expect(it.deletedWordIdx).toEqual([1])

    h = historyReduce(h, { type: 'delete_words', itemId: 'i1', idxs: [2, 3] })
    it = activeTimeline(h.present).items[0]
    expect(it.deletedWordIdx).toEqual([1, 2, 3])

    h = historyReduce(h, { type: 'set_item_variants', itemId: 'i1', variants: [{ id: 'v1', lang: 'zh', kind: 'translation', label: '中文' }] })
    it = activeTimeline(h.present).items[0]
    expect(it.variants?.length).toBe(1)
  })

  it('clean_script 移除填充词 / set_gap_cap / set_transcript_play_order', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1', transcript }) })
    h = historyReduce(h, { type: 'clean_script', itemId: 'i1', silenceFrames: 3, cutPadFrames: 1 })
    let it = activeTimeline(h.present).items[0]
    expect(it.deletedWordIdx).toEqual([0]) // '那个' 是填充词
    expect(it.silenceFrames).toBe(3)
    expect(it.cutPadFrames).toBe(1)

    h = historyReduce(h, { type: 'set_gap_cap', itemId: 'i1', afterWordIdx: 0, maxMs: 200 })
    it = activeTimeline(h.present).items[0]
    expect(it.gapCapsMs?.['0']).toBe(200)

    h = historyReduce(h, { type: 'set_transcript_play_order', itemId: 'i1', playOrder: [1, 2, 0] })
    it = activeTimeline(h.present).items[0]
    expect(it.transcriptPlayOrder).toEqual([1, 2, 0])

    h = historyReduce(h, { type: 'clear_edits', itemId: 'i1' })
    it = activeTimeline(h.present).items[0]
    expect(it.deletedWordIdx).toEqual([])
    expect(it.gapCapsMs).toBeNull()
    expect(it.transcriptPlayOrder).toBeNull()
  })

  it('set_item_transcript / fix_transcript_word / rename_speaker / reorder_track_items', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    h = historyReduce(h, { type: 'set_item_transcript', itemId: 'i1', transcript, generationId: 'g1' })
    let it = activeTimeline(h.present).items[0]
    expect(it.transcriptGenerationId).toBe('g1')
    expect(it.transcriptStale).toBe(false)

    h = historyReduce(h, { type: 'fix_transcript_word', itemId: 'i1', wordIdx: 1, text: 'Hi' })
    it = activeTimeline(h.present).items[0]
    expect(it.transcript?.[1].text).toBe('Hi')

    h = historyReduce(h, { type: 'rename_speaker', itemId: 'i1', fromSpeaker: 'A', toSpeaker: 'B' })
    it = activeTimeline(h.present).items[0]
    expect(it.transcript?.[2].speaker).toBe('B')

    // reorder_track_items 重排同轨道
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i2' }) })
    h = historyReduce(h, { type: 'reorder_track_items', track: 'V1', orderedIds: ['i2', 'i1'], starts: { i2: 0, i1: 90 } })
    const items = activeTimeline(h.present).items
    expect(items.map((i) => i.id)).toEqual(['i2', 'i1'])
    expect(items[0].startFrame).toBe(0)
    expect(items[1].startFrame).toBe(90)
  })

  it('set_asset_transcription 无效 id 返回原 doc', () => {
    let h = initHistory(defaultProject())
    const before = h
    h = historyReduce(h, { type: 'set_asset_transcription', assetId: '不存在', transcript })
    expect(h).toBe(before)
  })
})

describe('项目级 多时间线 create/switch/duplicate/delete', () => {
  it('create_timeline + switch_timeline', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'create_timeline', timeline: timeline('tl2', '时间线 2'), activate: true })
    expect(h.present.activeTimelineId).toBe('tl2')
    expect(h.present.timelines.length).toBe(2)

    h = historyReduce(h, { type: 'switch_timeline', timelineId: 'tl1' })
    expect(h.present.activeTimelineId).toBe('tl1')
  })

  it('duplicate_timeline 深拷贝内容并排序', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1' }) })
    const order0 = activeTimeline(h.present).order ?? 0
    h = historyReduce(h, { type: 'duplicate_timeline', timelineId: 'tl1', newId: 'tl2', name: '副本' })
    const dup = h.present.timelines.find((t) => t.id === 'tl2')
    expect(dup).toBeDefined()
    expect(dup?.name).toBe('副本')
    expect(dup?.order).toBe(order0 + 1)
    expect(dup?.items.length).toBe(1)
  })

  it('delete_timeline 激活切换到剩余首条', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'create_timeline', timeline: timeline('tl2', '时间线 2'), activate: true })
    h = historyReduce(h, { type: 'delete_timeline', timelineId: 'tl2' })
    expect(h.present.timelines.length).toBe(1)
    expect(h.present.activeTimelineId).toBe('tl1')

    // 无效 id
    const before = h
    h = historyReduce(h, { type: 'rename_timeline', timelineId: '不存在', name: 'x' })
    expect(h).toBe(before)
  })

  it('rename_timeline / retarget_timeline / set_timeline_hidden / set_full_state', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'rename_timeline', timelineId: 'tl1', name: '重命名' })
    expect(h.present.timelines[0].name).toBe('重命名')

    h = historyReduce(h, { type: 'retarget_timeline', timelineId: 'tl1', width: 1280, height: 720, fit: 'contain' })
    let tl = h.present.timelines[0]
    expect(tl.width).toBe(1280)
    expect(tl.height).toBe(720)
    expect(tl.fit).toBe('contain')

    h = historyReduce(h, { type: 'set_timeline_hidden', timelineId: 'tl1', hidden: true })
    expect(h.present.timelines[0].hidden).toBe(true)

    h = historyReduce(h, { type: 'set_full_state', patch: { selectedIds: ['i1'], watermark: { text: 'wm' } } })
    tl = activeTimeline(h.present)
    expect(tl.selectedIds).toEqual(['i1'])
    expect(tl.watermark?.text).toBe('wm')
  })

  it('set_design_style / patch_design_style / canonicalize_asset / set_project_doc', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'set_design_style', style: { theme: 'dark' } })
    expect(h.present.designStyle).toEqual({ theme: 'dark' })

    h = historyReduce(h, { type: 'patch_design_style', patch: { accent: 'red' } })
    expect(h.present.designStyle).toEqual({ theme: 'dark', accent: 'red' })

    h = historyReduce(h, { type: 'add_asset', asset: { id: 'dup', name: 'x', kind: 'video' } })
    h = historyReduce(h, { type: 'add_asset', asset: { id: 'canon', name: 'y', kind: 'video' } })
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1', sourceAssetId: 'dup' }) })
    h = historyReduce(h, { type: 'canonicalize_asset', duplicateId: 'dup', canonicalId: 'canon' })
    expect(h.present.assets.some((a) => a.id === 'dup')).toBe(false)
    expect(activeTimeline(h.present).items[0].sourceAssetId).toBe('canon')

    const nextDoc = defaultProject()
    h = historyReduce(h, { type: 'set_project_doc', doc: nextDoc })
    // set_project_doc 也必须维持单调 docVersion，避免旧快照回退 OCC 版本。
    expect(h.present).not.toBe(nextDoc)
    expect(h.present.docVersion).toBeGreaterThan(1)
    expect({ ...h.present, docVersion: nextDoc.docVersion }).toEqual(nextDoc)
  })
})

describe('多机位 set_canvas/add_multicam_decision', () => {
  it('set_canvas & set_multicam_groups & add_multicam_decision & link', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'set_canvas', width: 1280, height: 720, fit: 'contain' })
    let tl = activeTimeline(h.present)
    expect(tl.width).toBe(1280)
    expect(tl.height).toBe(720)
    expect(tl.fit).toBe('contain')

    const group: MulticamGroup = { id: 'g1', referenceAngleId: 'a1', masterAngleId: 'a2', decisions: [] }
    h = historyReduce(h, { type: 'set_multicam_groups', groups: [group] })
    h = historyReduce(h, { type: 'add_multicam_decision', groupId: 'g1', fromFrame: 0, toFrame: 30, angleId: 'a1', decisionId: 'd1' })
    tl = activeTimeline(h.present)
    expect(tl.multicamGroups?.[0].decisions?.length).toBe(1)
    expect(tl.multicamGroups?.[0].decisions?.[0].id).toBe('d1')

    const link: TimelineLinkGroup = { id: 'l1', itemIds: ['i1'], anchorItemId: 'i1', mode: 'linked' }
    h = historyReduce(h, { type: 'add_link_group', group: link })
    tl = activeTimeline(h.present)
    expect(tl.linkGroups?.length).toBe(1)
  })

  it('tighten_track 紧凑排列', () => {
    let h = initHistory(defaultProject())
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i1', startFrame: 100, durationInFrames: 30 }) })
    h = historyReduce(h, { type: 'add_item', item: item({ id: 'i2', startFrame: 200, durationInFrames: 60 }) })
    h = historyReduce(h, { type: 'tighten_track', track: 'V1' })
    const items = activeTimeline(h.present).items
    expect(items[0].startFrame).toBe(0)
    expect(items[1].startFrame).toBe(30)
  })
})
