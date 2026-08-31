// 内部 server run 的 claim/settle 客户端（链路 A，对齐 src/agent/serverRunToolExecutor.ts）。
// browser 订阅 SSE 事件流，收到 tool_request 后 claim → executeTool 执行 → settle 回传结果。

import { newId } from '../editor/commands'
import type { ProjectDoc } from '../editor/types'
import { SUPPORTED_TOOL_NAMES, type ExecuteTool, type ToolContext } from '../agent/tools'

export interface ToolCallEvent {
  name: string
  args: Record<string, unknown>
  result?: Record<string, unknown>
}

export interface ServerRunHandlers {
  onState(doc: ProjectDoc): void
  onAssistant(text: string): void
  onToolCall(name: string, args: Record<string, unknown>): void
  onToolResult(result: Record<string, unknown>): void
  onApprovalRequest(name: string, args: Record<string, unknown>): Promise<'approved' | 'rejected'>
  onError(message: string): void
  onDone(): void
}

interface SseEvent {
  event: string
  data: Record<string, unknown>
}

function parseSse(raw: string): SseEvent | null {
  let event = 'message'
  let data = ''
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  try {
    return { event, data: JSON.parse(data) as Record<string, unknown> }
  } catch {
    return { event, data: {} }
  }
}

async function claim(runId: string, toolCallId: string, claimId: string): Promise<boolean> {
  const res = await fetch(`/api/agent-runs/${runId}/tool-claim`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ toolCallId, claimId }),
  })
  // jimanweb 统一 ResultResponse 包装：{ code, data, success }，claim 结果在 data.ok
  const body = (await res.json()) as { success?: boolean; data?: { ok?: boolean } }
  return body.success === true && body.data?.ok === true
}

async function settle(runId: string, toolCallId: string, claimId: string, argsDigest: string, result: Record<string, unknown>): Promise<void> {
  await fetch(`/api/agent-runs/${runId}/tool-result`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ toolCallId, claimId, argsDigest, result }),
  })
}

async function approve(runId: string, toolCallId: string, decision: 'approved' | 'rejected'): Promise<void> {
  await fetch(`/api/agent-runs/${runId}/approval`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ toolCallId, decision }),
  })
}

// 消费 run 的 SSE 事件流，对每个 tool_request 做 claim → execute → settle。
export async function streamServerRun(
  runId: string,
  executeTool: ExecuteTool,
  ctx: ToolContext,
  handlers: ServerRunHandlers,
): Promise<void> {
  const res = await fetch(`/api/agent-runs/${runId}/events`, { headers: { Accept: 'text/event-stream' } })
  if (!res.ok || !res.body) {
    handlers.onError(`events HTTP ${res.status}`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const ev = parseSse(raw)
      if (!ev) continue

      switch (ev.event) {
        case 'state':
          handlers.onState(ev.data as unknown as ProjectDoc)
          break
        case 'assistant':
          handlers.onAssistant((ev.data.text as string) ?? '')
          break
        case 'error':
          handlers.onError((ev.data.message as string) ?? 'unknown error')
          break
        case 'done':
          handlers.onDone()
          return
        case 'approval_request': {
          const toolCallId = (ev.data.toolCallId as string) ?? ''
          const name = (ev.data.name as string) ?? ''
          const arguments_ = (ev.data.arguments as Record<string, unknown>) ?? {}
          // 挂起等用户弹框决定 approve/reject，再回传 server
          const decision = await handlers.onApprovalRequest(name, arguments_)
          await approve(runId, toolCallId, decision)
          break
        }
        case 'tool_request': {
          const toolCallId = (ev.data.toolCallId as string) ?? ''
          const name = (ev.data.name as string) ?? ''
          const arguments_ = (ev.data.arguments as Record<string, unknown>) ?? {}
          const argsDigest = (ev.data.argsDigest as string) ?? ''
          const claimId = newId()

          // claim → 执行 → settle（server 侧在 wait_for_tool_result 挂起，这里串行即可）
          handlers.onToolCall(name, arguments_)
          const claimed = await claim(runId, toolCallId, claimId)
          const result = claimed
            ? executeTool(name, arguments_, ctx)
            : { ok: false, error: 'claim failed' }
          handlers.onToolResult(result)
          await settle(runId, toolCallId, claimId, argsDigest, result)
          break
        }
      }
    }
  }
}

// 便捷封装：创建 run（延迟执行）+ start，然后订阅事件流。
export async function createAndStartRun(
  message: string,
  state: ProjectDoc,
  executeTool: ExecuteTool,
  ctx: ToolContext,
  handlers: ServerRunHandlers,
): Promise<void> {
  const createRes = await fetch('/api/agent-runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, state, supportedTools: SUPPORTED_TOOL_NAMES }),
  })
  // jimanweb 统一 ResultResponse 包装：runId 在 data 里
  const created = (await createRes.json()) as { success?: boolean; data?: { runId?: string } }
  const runId = created.data?.runId
  if (!runId) {
    handlers.onError('create run failed')
    return
  }
  await fetch(`/api/agent-runs/${runId}/start`, { method: 'POST' })
  await streamServerRun(runId, executeTool, ctx, handlers)
}
