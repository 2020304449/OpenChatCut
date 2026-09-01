import type { AgentProposal, ProposalCoordinator, ProposalResult } from '../agent/proposal'
import { SUPPORTED_TOOL_SCHEMAS } from '../agent/toolSchemas'
import { activeTimeline, type ProjectDoc } from '../editor/types'

export interface ToolCallEvent {
  name: string
  args: Record<string, unknown>
  result?: Record<string, unknown>
}

export interface ServerRunHandlers {
  onState(state: Record<string, unknown>): void
  onAssistant(text: string): void
  onToolCall(name: string, args: Record<string, unknown>): void
  onToolResult(result: Record<string, unknown>): void
  onApprovalRequest(name: string, args: Record<string, unknown>): Promise<'approved' | 'rejected'>
  onApprovedSideEffect(name: string, args: Record<string, unknown>): Promise<Record<string, unknown>>
  onProposalResult?(result: Record<string, unknown>): void
  onError(message: string): void
  onDone(): void
}

export interface CreateRunOptions {
  message: string
  projectId: string
  state: ProjectDoc
  proposalCoordinator: ProposalCoordinator
  handlers: ServerRunHandlers
  maxPoints?: number
}

interface SseEvent {
  id?: string
  event: string
  data: Record<string, unknown>
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

/** SSE data 只在边界解析一次，业务分支不再各自断言同一份未知数据。 */
export function parseSse(raw: string): SseEvent | null {
  let id: string | undefined
  let event = 'message'
  const dataLines: string[] = []
  // SSE 允许 data 跨多行；先拼接再 JSON.parse，避免长事件被截成半个对象。
  for (const line of raw.replaceAll('\r\n', '\n').split('\n')) {
    if (line.startsWith('id:')) id = line.slice(3).trim()
    else if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (dataLines.length === 0) return null
  try {
    return { id, event, data: asRecord(JSON.parse(dataLines.join('\n'))) }
  } catch {
    return { id, event, data: {} }
  }
}

function decodeProposal(data: Record<string, unknown>): AgentProposal | null {
  const proposalId = typeof data.proposalId === 'string' ? data.proposalId : ''
  const baseDocVersion = typeof data.baseDocVersion === 'number' ? data.baseDocVersion : NaN
  if (!proposalId || !Number.isSafeInteger(baseDocVersion) || !Array.isArray(data.ops)) return null
  // 只接受受限结构，任何缺少调用 ID/名称的事件直接丢弃，避免 settle 错配其它轮次。
  const ops = data.ops.map((raw) => {
    const op = asRecord(raw)
    return {
      toolCallId: typeof op.toolCallId === 'string' ? op.toolCallId : '',
      name: typeof op.name === 'string' ? op.name : '',
      arguments: asRecord(op.arguments),
    }
  })
  if (ops.some((op) => !op.toolCallId || !op.name)) return null
  return {
    proposalId,
    baseDocVersion,
    evidence: typeof data.evidence === 'string' ? data.evidence : '',
    mode: 'autonomous',
    ops,
  }
}

async function postJson(path: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = asRecord(await response.json().catch(() => ({})))
  // 网关成功 HTTP 也可能返回业务失败，两个层次都检查才能避免把错误当作已结算。
  if (!response.ok || payload.success === false) {
    const message = typeof payload.message === 'string' ? payload.message : `HTTP ${response.status}`
    throw new Error(message)
  }
  return asRecord(payload.data)
}

async function settleProposal(runId: string, result: ProposalResult | Record<string, unknown>): Promise<void> {
  await postJson(`/api/agent-runs/${runId}/settle-proposal`, {
    proposalId: String(result.proposalId ?? ''),
    result,
  })
}

async function approve(runId: string, proposalId: string, decision: 'approved' | 'rejected'): Promise<void> {
  await postJson(`/api/agent-runs/${runId}/approval`, { proposalId, decision })
}

/**
 * 消费 replay-then-live 事件流。事件 ID 去重处理网络层重放，ProposalCoordinator 再处理
 * proposalId 重放；两层幂等边界保证“服务端已收到 settle、浏览器却未收到响应”时不会重复编辑。
 */
export async function streamServerRun(
  runId: string,
  proposalCoordinator: ProposalCoordinator,
  handlers: ServerRunHandlers,
): Promise<void> {
  const response = await fetch(`/api/agent-runs/${runId}/events`, { headers: { Accept: 'text/event-stream' } })
  if (!response.ok || !response.body) throw new Error(`events HTTP ${response.status}`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const seenEventIds = new Set<string>()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replaceAll('\r\n', '\n')

    let separator: number
    while ((separator = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, separator)
      buffer = buffer.slice(separator + 2)
      const event = parseSse(raw)
      if (!event || (event.id && seenEventIds.has(event.id))) continue
      if (event.id) seenEventIds.add(event.id)

      switch (event.event) {
        case 'state':
          handlers.onState(event.data)
          break
        case 'assistant':
          handlers.onAssistant(typeof event.data.text === 'string' ? event.data.text : '')
          break
        case 'proposal': {
          const proposal = decodeProposal(event.data)
          if (!proposal) throw new Error('INVALID_PROPOSAL_EVENT')
          proposal.ops.forEach((op) => handlers.onToolCall(op.name, op.arguments))
          const result = proposalCoordinator.apply(proposal)
          // 先把每个 op 的结果展示给用户，再通知 Java 解除等待，保证 UI 与服务端状态一致。
          result.results.forEach((opResult) => handlers.onToolResult(opResult.result))
          await settleProposal(runId, result)
          break
        }
        case 'approval_request': {
          const proposalId = typeof event.data.proposalId === 'string' ? event.data.proposalId : ''
          const op = asRecord(event.data.op)
          const name = typeof op.name === 'string' ? op.name : ''
          const args = asRecord(op.arguments)
          if (!proposalId || !name) throw new Error('INVALID_APPROVAL_EVENT')
          // 重连时服务端会 replay 已完成审批；本地 settled 集合让这类事件成为无副作用 no-op。
          if (proposalCoordinator.settledProposalIds.has(proposalId)) break

          handlers.onToolCall(name, args)
          // 审批是副作用的唯一闸门，编辑 Proposal 不经过此分支。
          const decision = await handlers.onApprovalRequest(name, args)
          await approve(runId, proposalId, decision)
          if (decision === 'approved') {
            let sideEffectResult: Record<string, unknown>
            try {
              sideEffectResult = await handlers.onApprovedSideEffect(name, args)
            } catch (error) {
              sideEffectResult = { ok: false, error: error instanceof Error ? error.message : String(error) }
            }
            handlers.onToolResult(sideEffectResult)
            const settledSideEffect: ProposalResult = {
              ok: sideEffectResult.ok === true,
              proposalId,
              docVersion: proposalCoordinator.getCurrentDocVersion(),
              results: [{ toolCallId: String(op.toolCallId ?? ''), name, result: sideEffectResult }],
              failedResults: sideEffectResult.ok === true
                ? []
                : [{ toolCallId: String(op.toolCallId ?? ''), name, result: sideEffectResult }],
            }
            await settleProposal(runId, settledSideEffect)
            proposalCoordinator.remember(proposalId, settledSideEffect)
          } else {
            // 拒绝也必须结算当前 proposal，否则 Java 会一直阻塞到 600 秒导出超时；
            // 结算结果作为普通工具失败回灌，run 继续下一轮而不是被用户取消终止。
            const cancelled = { ok: false, error: '用户取消了导出操作' }
            handlers.onToolResult(cancelled)
            await settleProposal(runId, {
              ok: false,
              proposalId,
              docVersion: proposalCoordinator.getCurrentDocVersion(),
              results: [{ toolCallId: String(op.toolCallId ?? ''), name, result: cancelled }],
              failedResults: [{ toolCallId: String(op.toolCallId ?? ''), name, result: cancelled }],
              error: cancelled.error,
            })
            proposalCoordinator.remember(proposalId, {
              ok: false,
              proposalId,
              docVersion: proposalCoordinator.getCurrentDocVersion(),
              results: [{ toolCallId: String(op.toolCallId ?? ''), name, result: cancelled }],
              failedResults: [{ toolCallId: String(op.toolCallId ?? ''), name, result: cancelled }],
              error: cancelled.error,
            })
          }
          break
        }
        case 'proposal_result':
          handlers.onProposalResult?.(event.data)
          break
        case 'error':
          handlers.onError(typeof event.data.message === 'string' ? event.data.message : 'unknown error')
          break
        case 'done':
          handlers.onDone()
          return
      }
    }
    if (done) return
  }
}

/** 构造不超过 2KB 的结构摘要；完整工程只保留在浏览器和工程存储中。 */
export function buildStateSummary(doc: ProjectDoc): Record<string, unknown> {
  const timeline = activeTimeline(doc)
  const trackCounts: Record<string, number> = {}
  for (const item of timeline.items) trackCounts[item.track] = (trackCounts[item.track] ?? 0) + 1
  const assetKinds: Record<string, number> = {}
  for (const asset of doc.assets) {
    const kind = asset.kind.slice(0, 24)
    assetKinds[kind] = (assetKinds[kind] ?? 0) + 1
  }
  const summary = {
    activeTimeline: {
      id: timeline.id.slice(0, 64), name: timeline.name.slice(0, 80), fps: timeline.fps,
      width: timeline.width, height: timeline.height, trackCounts,
      selectedIds: (timeline.selectedIds ?? []).slice(0, 8),
    },
    timelineCount: doc.timelines.length,
    assetCount: doc.assets.length,
    assetKinds,
    hint: '片段、转场、字幕和素材细节请按需调用 read_* 工具',
  }
  if (new TextEncoder().encode(JSON.stringify(summary)).byteLength <= 2048) return summary
  return {
    activeTimeline: { id: timeline.id.slice(0, 64), fps: timeline.fps },
    timelineCount: doc.timelines.length,
    assetCount: doc.assets.length,
    hint: '工程较大，细节请调用 read_* 工具',
  }
}

/** create 已包含启动语义，成功后直接订阅事件，不再调用旧 start 端点。 */
export async function createAndStreamRun(options: CreateRunOptions): Promise<void> {
  const created = await postJson('/api/agent-runs', {
    message: options.message,
    projectId: options.projectId,
    stateSummary: buildStateSummary(options.state),
    docVersion: options.state.docVersion,
    supportedTools: SUPPORTED_TOOL_SCHEMAS,
    acceptanceMode: 'autonomous',
    ...(options.maxPoints === undefined ? {} : { maxPoints: options.maxPoints }),
  })
  const runId = typeof created.runId === 'string' ? created.runId : ''
  if (!runId) throw new Error('create run failed: missing runId')
  await streamServerRun(runId, options.proposalCoordinator, options.handlers)
}
