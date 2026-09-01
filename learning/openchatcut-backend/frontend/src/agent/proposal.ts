import { makeDraft } from '../editor/draft'
import type { ProjectDoc } from '../editor/types'
import { BROWSER_EDIT_TOOL_NAMES } from './toolSchemas'
import type { ExecuteTool } from './tools'

export interface ProposalOp {
  toolCallId: string
  name: string
  arguments: Record<string, unknown>
}

export interface AgentProposal {
  proposalId: string
  baseDocVersion: number
  evidence: string
  mode: 'autonomous'
  ops: ProposalOp[]
}

export interface ProposalOpResult {
  toolCallId: string
  name: string
  result: Record<string, unknown>
}

export interface ProposalResult {
  ok: boolean
  proposalId: string
  docVersion: number
  results: ProposalOpResult[]
  failedResults: ProposalOpResult[]
  error?: string
}

export interface ProposalDependencies {
  getDoc(): ProjectDoc
  commitProposal(doc: ProjectDoc): void
  executeTool: ExecuteTool
}

const EDIT_TOOL_NAMES = new Set(BROWSER_EDIT_TOOL_NAMES)

/**
 * 一个协调器只服务于一个浏览器编辑器实例。结果缓存与 settled 集合必须跨 SSE 重连保留，
 * 这样服务端重放同一 proposal 时，浏览器只会回传第一次结果，不会再次修改文档。
 */
export class ProposalCoordinator {
  readonly settledProposalIds = new Set<string>()
  private readonly settledResults = new Map<string, ProposalResult>()

  constructor(private readonly deps: ProposalDependencies) {}

  getCurrentDocVersion(): number {
    return this.deps.getDoc().docVersion
  }

  /** 记录被用户拒绝的副作用 Proposal，防止 SSE 重放再次弹出审批框。 */
  remember(proposalId: string, result: ProposalResult): void {
    this.settledProposalIds.add(proposalId)
    this.settledResults.set(proposalId, result)
  }

  apply(proposal: AgentProposal): ProposalResult {
    // settledResults 是浏览器侧的幂等屏障：SSE 可能重放同一 proposal，重复调用必须直接返回首次结果。
    const cached = this.settledResults.get(proposal.proposalId)
    if (cached) return cached

    const current = this.deps.getDoc()
    // baseDocVersion 是乐观并发控制点。用户在等待审批期间手动编辑，旧 proposal 只能失败，不能覆盖新内容。
    if (proposal.baseDocVersion !== current.docVersion) {
      return this.settle(proposal, this.failureForAll(
        proposal,
        `STALE_PROPOSAL: baseDocVersion=${proposal.baseDocVersion}, currentDocVersion=${current.docVersion}`,
      ))
    }

    if (proposal.ops.length === 0) {
      return this.settle(proposal, {
        ok: false,
        proposalId: proposal.proposalId,
        docVersion: current.docVersion,
        results: [],
        failedResults: [],
        error: 'EMPTY_PROPOSAL',
      })
    }

    // 所有 op 都只写草稿。即使中途失败，也继续执行后续 op 以收集完整 failedResults；
    // 真文档在全包成功前不会被替换，因此任何失败都能无条件丢弃草稿完成整体回滚。
    const draft = makeDraft(current)
    const ctx = { getDoc: draft.getDoc, commands: draft.commands }
    const results: ProposalOpResult[] = proposal.ops.map((op) => {
      let result: Record<string, unknown>
      if (!EDIT_TOOL_NAMES.has(op.name)) {
        // 服务端可能缓存了旧 schema；未知工具按单 op 失败，仍继续收集其它 op 的失败原因。
        result = { ok: false, error: `UNSUPPORTED_PROPOSAL_TOOL: ${op.name}` }
      } else {
        try {
          result = this.deps.executeTool(op.name, op.arguments, ctx)
        } catch (error) {
          result = { ok: false, error: error instanceof Error ? error.message : String(error) }
        }
      }
      return { toolCallId: op.toolCallId, name: op.name, result }
    })
    const failedResults = results.filter(({ result }) => result.ok !== true)

    if (failedResults.length > 0) {
      return this.settle(proposal, {
        ok: false,
        proposalId: proposal.proposalId,
        docVersion: current.docVersion,
        results,
        failedResults,
        error: 'PROPOSAL_APPLY_FAILED',
      })
    }

    // 只读 Proposal 不制造空历史节点；发生编辑时，无论 op 数量多少都只提交一次，
    // EditorStore 在这个唯一提交点递增 docVersion，因此一次撤销即可回退整包编辑。
    const changed = draft.countActions() > 0
    if (changed) this.deps.commitProposal(draft.getDoc())
    const docVersion = changed ? current.docVersion + 1 : current.docVersion
    return this.settle(proposal, {
      ok: true,
      proposalId: proposal.proposalId,
      docVersion,
      results,
      failedResults: [],
    })
  }

  private failureForAll(proposal: AgentProposal, error: string): ProposalResult {
    const failedResults = proposal.ops.map((op) => ({
      toolCallId: op.toolCallId,
      name: op.name,
      result: { ok: false, error },
    }))
    return {
      ok: false,
      proposalId: proposal.proposalId,
      docVersion: this.deps.getDoc().docVersion,
      results: failedResults,
      failedResults,
      error,
    }
  }

  private settle(proposal: AgentProposal, result: ProposalResult): ProposalResult {
    // 先缓存完整结果再返回，确保网络重试、SSE replay 和调用方重入都不会再次执行编辑。
    this.settledProposalIds.add(proposal.proposalId)
    this.settledResults.set(proposal.proposalId, result)
    return result
  }
}
