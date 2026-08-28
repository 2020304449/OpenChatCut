// 外部 MCP agent 的 broker 长轮询客户端（链路 B，对齐 src/agent/useExternalAgentBridge.ts）。
// browser register 上报工具换 capability → 长轮询取调用 → 在 edit-session draft 上执行 → settle 回传。

import type { ProjectDoc } from '../editor/types'
import { beginEditSession, type EditSession } from '../agent/session'
import type { ExecuteTool, ToolContext } from '../agent/tools'

const CAPABILITY_HEADER = 'X-OpenChatCut-Editor-Registration'

export interface ExternalToolSchema {
  name: string
  description?: string
}

export interface ExternalCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface RegisterResult {
  registrationCapability: string
  ownershipEpoch: number
}

export interface ExternalBridgeDeps {
  projectId: string
  editorId: string
  baseRevision: string
  tools: ExternalToolSchema[]
  executeTool: ExecuteTool
  getBaseDoc(): ProjectDoc
  apply(doc: ProjectDoc): void
}

// ── 三段 HTTP 原语 ─────────────────────────────────────────────────────────

export async function registerEditorBridge(
  projectId: string,
  editorId: string,
  baseRevision: string,
  tools: ExternalToolSchema[],
): Promise<RegisterResult> {
  const res = await fetch('/api/external-agent/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projectId, editorId, baseRevision, tools }),
  })
  const body = (await res.json()) as { registrationCapability?: string; ownershipEpoch?: number }
  if (!body.registrationCapability) throw new Error('register failed')
  return { registrationCapability: body.registrationCapability, ownershipEpoch: body.ownershipEpoch ?? 0 }
}

export async function pollEditorCall(projectId: string, capability: string): Promise<ExternalCall | null> {
  const res = await fetch(`/api/external-agent/poll?projectId=${encodeURIComponent(projectId)}`, {
    headers: { [CAPABILITY_HEADER]: capability },
  })
  if (!res.ok) throw new Error(`poll HTTP ${res.status}`)
  const body = (await res.json()) as { call?: ExternalCall | null }
  return body.call ?? null
}

export async function settleEditorCall(
  projectId: string,
  capability: string,
  callId: string,
  outcome: string,
  result: Record<string, unknown>,
  baseRevision: string,
): Promise<void> {
  await fetch(`/api/external-agent/result?projectId=${encodeURIComponent(projectId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', [CAPABILITY_HEADER]: capability },
    body: JSON.stringify({ callId, outcome, result, baseRevision }),
  })
}

// ── 生命周期工具路由（begin/get/review/discard + 编辑工具） ────────────────

const LIFECYCLE_TOOLS = new Set(['begin_edit_session', 'get_edit_session', 'review_edit_session', 'discard_edit_session'])

// 全局只读工具：不经 edit-session，直接读 browser 真库（对齐 externalGlobalReadSchemas）。
const READ_TOOLS = new Set(['read_timeline', 'read_project', 'read_transcript'])

export interface ExternalRuntime {
  session: EditSession | null
  baseRevision: string
  /** 处理一个外部调用，返回结算结果 */
  execute(call: ExternalCall): Record<string, unknown>
}

export function createExternalRuntime(deps: ExternalBridgeDeps): ExternalRuntime {
  const rt: ExternalRuntime = {
    session: null,
    baseRevision: deps.baseRevision,
    execute(call) {
      switch (call.name) {
        case 'begin_edit_session': {
          const mode = (call.arguments.approvalMode === 'manual' ? 'manual' : 'auto')
          rt.session = beginEditSession(deps.getBaseDoc(), mode)
          return { ok: true, editSessionId: rt.session.sessionId, approvalMode: mode }
        }
        case 'get_edit_session':
          return rt.session
            ? { ok: true, editSessionId: rt.session.sessionId, pendingActions: rt.session.draft.countActions() }
            : { ok: false, error: 'no active edit session' }
        case 'review_edit_session': {
          const session = rt.session
          if (!session) return { ok: false, error: 'no active edit session' }
          const reviewed = session.review()
          const applied = session.approvalMode === 'auto'
          if (applied) deps.apply(reviewed)
          rt.session = null
          return { ok: true, applied }
        }
        case 'discard_edit_session':
          if (rt.session) rt.session.discard()
          rt.session = null
          return { ok: true }
        default:
          break
      }
      // 全局只读工具：无需 edit-session，直接读真库（read 只用 getDoc，不用 commands）。
      if (READ_TOOLS.has(call.name)) {
        return deps.executeTool(call.name, call.arguments, {
          getDoc: deps.getBaseDoc,
          commands: {} as ToolContext['commands'],
        })
      }
      // 编辑工具：必须在 draft 上执行
      if (!rt.session) return { ok: false, error: '请先 begin_edit_session' }
      return deps.executeTool(call.name, call.arguments, rt.session.toolContext)
    },
  }
  return rt
}

// ── 轮询循环（骨架：单次 pollOnce 由调用方驱动，避免无限循环失控） ────────

// 注册一次拿 capability，之后循环 pollAndSettle；返回 false 表示本轮无调用（长轮询超时）。
export async function pollAndSettle(deps: ExternalBridgeDeps, rt: ExternalRuntime, capability: string): Promise<boolean> {
  const call = await pollEditorCall(deps.projectId, capability)
  if (!call) return false
  const result = rt.execute(call)
  await settleEditorCall(deps.projectId, capability, call.id, 'applied', result, rt.baseRevision)
  return true
}
