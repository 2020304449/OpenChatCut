// executeTool（工具==命令）+ edit-session 三段式 的集成测试。
import { describe, expect, it } from 'vitest'
import { beginEditSession } from './session'
import { executeTool, SUPPORTED_TOOL_NAMES, type ToolContext } from './tools'
import { buildCommands } from '../editor/commands'
import { historyReduce, initHistory, type History } from '../editor/reduce'
import { activeTimeline, defaultProject, type ProjectDoc } from '../editor/types'

// 用「真库」构建 ToolContext：commands 派发 → historyReduce 更新 doc（对齐 useEditor）
function storeCtx(initial: ProjectDoc = defaultProject()): { ctx: ToolContext; getDoc: () => ProjectDoc } {
  let h: History = initHistory(initial)
  const commands = buildCommands((a) => { h = historyReduce(h, a) })
  return { ctx: { getDoc: () => h.present, commands }, getDoc: () => h.present }
}

describe('executeTool 工具==命令', () => {
  it('edit_item adds / set_clip_volume / read_timeline', () => {
    const { ctx, getDoc } = storeCtx()
    const add = executeTool('edit_item', { adds: [{ type: 'solid', color: '#000000', track: 'V1', fromFrame: 0, durationInFrames: 90 }] }, ctx)
    expect(add.ok).toBe(true)
    const itemId = (add as { added: { itemId: string }[] }).added[0].itemId

    expect(executeTool('set_clip_volume', { itemId, volume: 0.5 }, ctx).ok).toBe(true)
    const item = activeTimeline(getDoc()).items.find((i) => i.id === itemId)
    expect(item?.volume).toBe(0.5)

    const read = executeTool('read_timeline', {}, ctx)
    expect(read.ok).toBe(true)
  })

  it('remove_item 找不到片段返回错误', () => {
    const { ctx } = storeCtx()
    const r = executeTool('remove_item', { itemId: '不存在' }, ctx)
    expect(r.ok).toBe(false)
  })

  it('edit_track 分发 create/delete', () => {
    const { ctx, getDoc } = storeCtx()
    expect(executeTool('edit_track', { action: 'create', track: 'V2', kind: 'video', name: '副轨' }, ctx).ok).toBe(true)
    expect(activeTimeline(getDoc()).tracks?.['V2']?.name).toBe('副轨')

    expect(executeTool('edit_track', { action: 'delete', track: 'V2' }, ctx).ok).toBe(true)
    expect(activeTimeline(getDoc()).tracks?.['V2']).toBeUndefined()
  })

  it('manage_timelines duplicate 产生第二条时间线', () => {
    const { ctx, getDoc } = storeCtx()
    const r = executeTool('manage_timelines', { action: 'duplicate', timelineId: 'tl1', name: '副本' }, ctx)
    expect(r.ok).toBe(true)
    expect(getDoc().timelines.length).toBe(2)
  })

  it('set_keyframe / set_clip_transform', () => {
    const { ctx, getDoc } = storeCtx()
    const add = executeTool('edit_item', { adds: [{ type: 'solid', color: '#000000', track: 'V1', fromFrame: 0, durationInFrames: 90 }] }, ctx) as { added: { itemId: string }[] }
    const itemId = add.added[0].itemId
    expect(executeTool('set_clip_transform', { itemId, patch: { x: 10, rotation: 45 } }, ctx).ok).toBe(true)
    expect(executeTool('set_keyframe', { itemId, prop: 'x', frame: 30, value: 200 }, ctx).ok).toBe(true)
    const item = activeTimeline(getDoc()).items.find((i) => i.id === itemId)
    expect(item?.transform?.x).toBe(10)
    expect(item?.keyframes?.['x']?.[0]?.value).toBe(200)
  })

  it('edit_item updates/deletes + authored text/solid', () => {
    const { ctx, getDoc } = storeCtx()
    const add = executeTool('edit_item', {
      adds: [
        { type: 'text', text: '标题', color: '#ffcc00', fromFrame: 0, durationInFrames: 60 },
        { type: 'solid', color: '#112233', durationInFrames: 45 },
      ],
    }, ctx) as { ok: boolean; added: { itemId: string }[] }
    expect(add.ok).toBe(true)
    const textId = add.added[0].itemId
    const text = activeTimeline(getDoc()).items.find((i) => i.id === textId)
    expect(text?.kind).toBe('text')
    expect(text?.props?.text).toBe('标题')

    // update：移动 + 改时长 + 音量
    expect(executeTool('edit_item', { updates: [{ itemId: textId, fromFrame: 10, durationInFrames: 100, volume: 0.5 }] }, ctx).ok).toBe(true)
    const moved = activeTimeline(getDoc()).items.find((i) => i.id === textId)
    expect(moved?.startFrame).toBe(10)
    expect(moved?.durationInFrames).toBe(100)
    expect(moved?.volume).toBe(0.5)

    // delete
    expect(executeTool('edit_item', { deletes: [{ itemId: textId }] }, ctx).ok).toBe(true)
    expect(activeTimeline(getDoc()).items.some((i) => i.id === textId)).toBe(false)
  })

  it('未知工具返回 not implemented', () => {
    const { ctx } = storeCtx()
    const r = executeTool('transcribe_track', {}, ctx)
    expect(r.ok).toBe(false)
    expect((r as { error: string }).error).toContain('not implemented')
  })

  it('SUPPORTED_TOOL_NAMES 每个名字 executeTool 都实现（不返回 not implemented）', () => {
    const { ctx } = storeCtx()
    for (const name of SUPPORTED_TOOL_NAMES) {
      const r = executeTool(name, {}, ctx) as { ok?: boolean; error?: string }
      // 允许返回 item not found / unknown action 等业务错误，只要不是 not implemented
      if (r.error !== undefined) {
        expect(r.error).not.toContain('not implemented')
      }
    }
  })
})

describe('edit-session 三段式', () => {
  it('begin → draft 上执行不污染真库 → review 落库', () => {
    const base = defaultProject()
    const session = beginEditSession(base, 'auto')

    // 在 draft 上执行
    executeTool('edit_item', { adds: [{ type: 'solid', color: '#000000', track: 'V1', fromFrame: 0, durationInFrames: 90 }] }, session.toolContext)
    expect(activeTimeline(session.getDoc()).items.length).toBe(1)
    expect(activeTimeline(base).items.length).toBe(0) // 真库未污染

    // review 落库
    const reviewed = session.review()
    expect(activeTimeline(reviewed).items.length).toBe(1)
    expect(activeTimeline(base).items.length).toBe(0) // 原 base 仍不变（纯函数）
  })

  it('review 后 session 清空 actions', () => {
    const session = beginEditSession(defaultProject(), 'auto')
    executeTool('edit_item', { adds: [{ type: 'solid', color: '#000000', track: 'V1', fromFrame: 0, durationInFrames: 90 }] }, session.toolContext)
    session.review()
    // takeActions 已清空，再次 review 应无新改动
    const again = session.review()
    expect(activeTimeline(again).items.length).toBe(0)
  })
})
