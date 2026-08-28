// edit-session 三段式（对齐 src/agent/external-edit-session.ts）。
// 外部 MCP 客户端从不直接写 ProjectDoc：begin → 在 draft 上执行并记录 actions → review/apply 原子落库。
// manual 模式把「确认」交给 OpenChatCut UI，auto 模式立即 apply（骨架先实现 auto）。

import { newId } from '../editor/commands'
import { makeDraft, replayActions, type DraftEngine } from '../editor/draft'
import type { ProjectDoc } from '../editor/types'
import type { ToolContext } from './tools'

export type ApprovalMode = 'manual' | 'auto'

export interface EditSession {
  sessionId: string
  approvalMode: ApprovalMode
  base: ProjectDoc
  draft: DraftEngine
  /** 工具执行上下文指向 draft（不碰真库） */
  toolContext: ToolContext
  getDoc(): ProjectDoc
  /** review：把 draft 记录的 actions 重放到 base，返回待提交的新 doc（不落库） */
  review(): ProjectDoc
  /** 丢弃草稿 */
  discard(): void
}

export function beginEditSession(base: ProjectDoc, approvalMode: ApprovalMode = 'auto'): EditSession {
  const draft = makeDraft(base)
  return {
    sessionId: newId(),
    approvalMode,
    base,
    draft,
    toolContext: { getDoc: () => draft.getDoc(), commands: draft.commands },
    getDoc: () => draft.getDoc(),
    review: () => replayActions(base, draft.takeActions()),
    discard: () => { draft.takeActions() },
  }
}
