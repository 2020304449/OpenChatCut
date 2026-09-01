import { describe, expect, it } from 'vitest'
import { ProposalCoordinator } from './proposal'
import { executeTool } from './tools'
import { defaultProject } from '../editor/types'
import { useEditor } from '../editor/store'
import { SUPPORTED_TOOL_SCHEMAS } from './toolSchemas'

function setup() {
  const editor = useEditor(defaultProject())
  const coordinator = new ProposalCoordinator({
    getDoc: () => editor.doc.value,
    commitProposal: editor.commitProposal,
    executeTool,
  })
  return { editor, coordinator }
}

describe('Proposal 原子应用', () => {
  it('协商清单固定为 47 个编辑工具和唯一 submit_export 审批工具', () => {
    expect(SUPPORTED_TOOL_SCHEMAS).toHaveLength(48)
    expect(SUPPORTED_TOOL_SCHEMAS.filter((s) => s.function['x-requires-approval'])).toHaveLength(1)
    expect(SUPPORTED_TOOL_SCHEMAS.find((s) => s.function.name === 'submit_export')?.function['x-requires-approval']).toBe(true)
    expect(SUPPORTED_TOOL_SCHEMAS.filter((s) => s.function['x-read-only']).map((s) => s.function.name))
      .toEqual(expect.arrayContaining(['read_timeline', 'read_project', 'read_transcript', 'list_audio']))
  })

  it('同包多个编辑只提交一次并递增一个版本', () => {
    const { editor, coordinator } = setup()
    const result = coordinator.apply({
      proposalId: 'p1', baseDocVersion: 1, evidence: '', mode: 'autonomous',
      ops: [
        { toolCallId: 'a', name: 'edit_track', arguments: { action: 'create', track: 'V2', kind: 'video' } },
        { toolCallId: 'b', name: 'set_full_state', arguments: { patch: { selectedIds: [] } } },
      ],
    })
    expect(result.ok).toBe(true)
    expect(result.docVersion).toBe(2)
    expect(editor.doc.value.docVersion).toBe(2)
    expect(editor.doc.value.timelines[0].tracks?.V2).toBeDefined()
    expect(editor.canUndo.value).toBe(true)
  })

  it('任一 op 失败时整体回滚且返回 failedResults', () => {
    const { editor, coordinator } = setup()
    const result = coordinator.apply({
      proposalId: 'p2', baseDocVersion: 1, evidence: '', mode: 'autonomous',
      ops: [
        { toolCallId: 'a', name: 'edit_track', arguments: { action: 'create', track: 'V2', kind: 'video' } },
        { toolCallId: 'b', name: 'not_a_tool', arguments: {} },
      ],
    })
    expect(result.ok).toBe(false)
    expect(result.failedResults).toHaveLength(1)
    expect(editor.doc.value.docVersion).toBe(1)
    expect(editor.doc.value.timelines[0].tracks?.V2).toBeUndefined()
  })

  it('拒绝陈旧版本，并对重复 proposalId 返回同一结果而不重复提交', () => {
    const { editor, coordinator } = setup()
    const proposal = {
      proposalId: 'p3', baseDocVersion: 0, evidence: '', mode: 'autonomous' as const,
      ops: [{ toolCallId: 'a', name: 'clear_timeline', arguments: {} }],
    }
    const stale = coordinator.apply(proposal)
    const duplicate = coordinator.apply(proposal)
    expect(stale.error).toContain('STALE_PROPOSAL')
    expect(duplicate).toBe(stale)
    expect(coordinator.settledProposalIds.has('p3')).toBe(true)
    expect(editor.doc.value.docVersion).toBe(1)
  })
})
