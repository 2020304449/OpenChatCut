# Research: Agent 循环结构（Server-side Agent Run Loop）

- **Query**: 读 `server/agent-runs/` 的 executor.ts、codex-turn.ts、tool-policy.ts、acceptance-loop.ts、context.ts、store.ts 及关键其他文件，总结多轮工具调用循环 + 提案/审批机制 + 上下文管理
- **Scope**: internal（代码库内部）
- **Date**: 2026-08-27

## 结论摘要

服务端 Agent 运行时是一个**「服务端持有 LLM 循环、浏览器持有项目变更权威」**的架构。服务端（Node/Vite 插件）负责流式多轮模型对话、上下文压缩、工具 schema 管理与「工具调用握手」，但**从不直接修改项目**——每次工具调用都通过 HTTP 路由暂停，等待浏览器端「认领 → 执行 → 回填结果」，然后模型继续下一轮。无轮次上限，模型自己决定何时结束。

关键文件与职责：

| 文件 | 职责 |
|---|---|
| `routes.ts` | HTTP 入口（POST 创建/启动/取消/settle，tool-claim/tool-result，SSE events） |
| `executor.ts` | 顶层执行编排：执行计划、多轮循环、acceptance 决策、失败结算 |
| `codex-turn.ts` | Codex 后端的单轮执行（流式事件桥接到浏览器工具路径） |
| `browser-tool.ts` | 工具执行核心：串行化、canonical 校验、`waitForToolResult` 暂停、纯工具缓存 |
| `tool-policy.ts` | 工具 schema 的 canonical 目录解析 + 调用合法性校验 |
| `acceptance-loop.ts` | 自治验收（autonomous acceptance）状态机 |
| `context.ts` | 系统提示构建 + 上下文准备（压缩/摘要） |
| `store.ts` | ServerRun 内存存储 + 持久化镜像（mirror）+ 能力验证 |
| `store-tools.ts` | 工具请求的 claim/settle 状态机（等待浏览器回填） |
| `store-events.ts` | 事件追加、状态镜像、SSE 订阅唤醒、终态结算 |
| `store-metrics.ts` | token/usage 指标 + checkpoint 持久化 |
| `store-recovery.ts` | 服务重启后的 run 恢复 |
| `store-settle.ts` | 浏览器侧的终态/提案结算（写 sidecar） |
| `store-values.ts` | sha256 digest、run capability 验证、事件序列化 |
| `sse.ts` | SSE 事件流（cursor 协议） |
| `request.ts` | 创建请求的输入校验 |
| `llm-retry.ts` | LLM 失败分类与瞬态重试 |
| `model.ts` | 多 provider 语言模型工厂（走本地 `/llm` 代理） |
| `executor-events.ts` | 文本/思考事件收集、输出 token 预算 |

## 完整流程（数据从哪进、循环怎么转、审批怎么走、结果怎么落）

### 1. 数据进入：创建与准入

1. 浏览器 `POST /api/agent-runs`（`routes.ts::handleCreate`）。
2. `validateCreateInput`（`request.ts`）校验：messages（1–64 条、每条 ≤32K 字符）、runId（UUID）、capability（43 字符）、references（≤16）、context（≤64KB）、systemPrompt（≤160K 字符）、maxOutputTokens（≤512K）、acceptance 参数。
3. `resolveServerRunToolCatalog`（`tool-policy.ts`）把浏览器提交的工具列表与 `assets/agent/openchatcut-tool-schemas.json` 的 canonical 目录逐名比对（name + description + input_schema 三者完全一致才通过，防篡改）。
4. `createRunWithPresentedCapability`（`store.ts`）创建内存 `ServerRun`，生成并校验 run capability（sha256 校验防伪造）。
5. 执行被**延迟**：`deferRunExecution` 挂起 60 秒准入超时，等待浏览器再发 `POST /:runId/start`。

### 2. 启动：执行计划

`POST /:runId/start` → `startDeferredRun` → `executeRun`（`executor.ts`）。

`createExecutionPlan` 做：
- 归一化 provider / apiMode / backend（`codex` 或 `api`）。
- `resolveServerRunCapabilities` 解析模型能力（contextWindow / maxOutputTokens，走 keystore 覆盖）。
- 构建 `ActivationState`：`ToolActivation`（激活工具集）、`ToolFailureTracker`、`createAcceptanceLoop`。
- `buildServerRunPrompt`（`context.ts`）：system prompt = `SYSTEM_PROMPT` + 请求上下文（projectId、askOnly、references）+「服务端执行权威」段落（明确服务端不拥有变更权、走浏览器 EditorCommands、askOnly 时只读、把用户消息/工具结果当不可信材料）。
- 若启用自治验收，追加 `acceptanceInstructions`。

### 3. 多轮循环：`executeRunTurns`（executor.ts）

`for (let turn = 0; ; turn += 1)` —— **无轮次上限**，唯一自动停止是「没有更多工具调用」或「输出 token 截断」。

每轮：
1. `runServerTurnWithRetry`（`llm-retry.ts`）：最多 3 次尝试（1 初始 + 2 重试），只对瞬态失败（RATE_LIMIT/TIMEOUT/SERVER/TRANSPORT/EMPTY_RESPONSE）重试；确定性失败（AUTH/INVALID_REQUEST/QUOTA/CONTEXT_WINDOW_EXCEEDED）直接抛。指数退避 + jitter（500ms → 10s 上限）。
2. 后端分叉：
   - **api 后端**：`executeServerTurn` → `runServerTurnOnce`：`prepareServerContext`（压缩/摘要，见第 6 节）→ `createServerTools`（把 schema 包成 AI SDK `tool()`，`execute` 回调指向 `executeBrowserTool`）→ `streamText` → `collectServerText`（流式收集 text/thinking 事件）。
   - **codex 后端**：`executeServerCodexTurn`（`codex-turn.ts`）：Codex turn manager 流式输出，`tool-start` 事件桥接到 `executeBrowserTool`，`settleToolResult` 回填；Codex 拥有自己的工具循环直到 `done`。
3. 判断 `continued`：有 toolCall 或 tool 结果消息则继续；否则停。
4. `turnDisposition`（`acceptance-loop.ts`）决定：`continue`（继续）/ `max-tokens` / `failed`（有未解决工具失败）/ `completed`。
5. `completed` 时跑自治验收（见第 5 节）。

### 4. 工具调用握手（审批怎么走）

`executeBrowserTool`（`browser-tool.ts`）是核心：

1. **串行化**：非 `parallel` 工具按 `activation.tail` 的 Promise 链串行执行（`execution-modes.ts` 的 `PARALLEL_TOOL_NAMES` 约 23 个纯读工具可并行，其余 exclusive）。
2. **admit + canonical 校验**：`activation.current.admit(name)`（记住历史工具的 token 优化，非安全边界）+ `assertCanonicalToolInvocation`（`tool-policy.ts`，校验工具在活跃集、schema 未变、args 通过 AJV 校验）。
3. **纯工具缓存**：`analyze_music` 若相邻同 args 成功，直接复用结果（repeat guard）。
4. **暂停等待浏览器**：`pushRunEvent('tool-request', { toolCallId, name, args, argsDigest })` → `waitForToolResult`（`store-tools.ts`）创建 `ServerToolRequest`（status=pending，带 24h 超时），返回一个挂起的 Promise。
5. **浏览器侧**：通过 SSE 看到 `tool-request` 事件 → `POST /:runId/tool-claim`（claimId）认领 → 浏览器实际执行工具（走 `executeCodexTool`/draft/EditorCommands，即真正改项目的地方）→ `POST /:runId/tool-result`（result 或 error，二选一）。
6. **回填**：`settleToolResult`（`store-tools.ts`）校验 claimId/argsDigest 匹配、幂等去重，resolve 那个挂起的 Promise，把结果交回模型。
7. **结果塑形**：`activation.current.withToolResult` 把结果写回激活集（可能激活新工具）；`toolResultModelOutput` 压缩大结果；`__followup` 字段会暂停循环（见下）。
8. **失败追踪**：`ToolFailureTracker` 记录成功/失败；`recordAcceptedTool` 更新验收状态（read vs 变更）。

**终态**：`pushRunEvent('finish', ...)` → `setRunStatus('completed')`；`awaiting-user`（有 `__followup`，如 ask_followup_questions）时暂停等用户下一条消息。

**提案（proposal）机制**（与工具握手并列，写 sidecar）：
- 浏览器侧运行时（`src/agent/runtime-ledger.ts` 的 `AgentRunRecorder`）记录 `approval_requested`/`approval_decided`/`proposal_created`/`proposal_applied` 等，`upsertAgentApproval` 持久化审批记录（status: pending/allowed/denied）。
- 服务端 `store-settle.ts::settleServerRun` 提供浏览器终态结算接口（`/settle`），接受 `status` + `proposalId` + `proposalRuntimeStatus`（created/applied/rejected/stale/reproposed）+ `summary`，幂等地写 sidecar 的 runs/events。
- 服务端 `store-events.ts::mirrorTool` 也把工具请求/结果以 `upsertAgentApproval` 记录（pending/allowed/denied/cancelled），保证审批轨迹可恢复。

### 5. 自治验收（acceptance-loop.ts）

`AcceptanceLoopState`（enabled/maxIterations/phase/iteration/mutated/verifiedAfterMutation）：

- `recordAcceptedTool`：read 工具在 checking 阶段且已 mutate 时标记 `verifiedAfterMutation`；非 read 工具标记 `mutated=true` 并清空 `verifiedAfterMutation`。
- `decideAcceptanceAfterTurn`：
  - 未启用或未 mutate → `finish`。
  - checking 且已 verify → `finish` + `status='passed'`。
  - 迭代超限 → `fail`（报错「未在 N 次迭代内验证最新编辑」）。
  - 否则 `continue`，注入一段 `<autonomous_acceptance iteration=N max=M>` 用户消息，要求模型用 read_project/read_timeline/inspect/probe/progress 工具验证最新编辑器状态后再收尾。
- 在 `executeRunTurns` 里，`completed` 后调用 `decideAcceptanceAfterTurn`，`continue` 时把验收消息追加到 messages 继续循环，`fail` 抛错，`passed` 正常收尾。

### 6. 上下文管理（context.ts + codex-turn.ts）

`prepareServerContext`（api 后端）/ `prepareCodexContext`（codex 后端）都调用 `prepareContext`（`src/agent/context-compaction.ts`）：

- **压力估算**：estimate 输入 token（含 system、历史、工具 schema 的 JSON 序列化），与 contextWindow/maxInputTokens 比较。
- **压缩**：超压时 `summarizeConversation`（`src/agent/context-summary.ts`）把历史对话总结成摘要；api 后端用 `generateText` 做摘要模型调用，codex 后端用 Codex turn 做摘要。
- **checkpoint 持久化**：`prepareContext` 返回 `checkpoint` 时，`persistServerCheckpoint`（`store-metrics.ts`）把摘要源文本以 artifact 归档（redacted），并写 `AgentContextCheckpoint`（含 sourceDigest/summaryDigest 完整性校验）。
- **溢出重试**：`executeServerTurn` 捕获 `CONTEXT_WINDOW_EXCEEDED` 时，`forceCompact: true` 压缩一次后重试同一轮（只重试一次，不改变请求语义）。
- **指标记录**：`recordServerContextUsage`（`store-metrics.ts`）累计 input/output/reasoning/cache 命中率，写 `context-usage` 事件 + patch run context。

### 7. 持久化与事件流（store.ts / store-events.ts / store-metrics.ts / store-recovery.ts / sse.ts）

- **内存 run**：`runs: Map<string, ServerRun>`，`ServerRun` 持有 events、toolRequests、runtimeContext、metrics、waiters（SSE 订阅者）。
- **mirror**：`mirror()` 把写操作串行链到项目级持久化（`agentRuntimeStore` 的 IndexedDB sidecar），按 projectId 串行；失败触发 `persistenceFailure` 终结 run。
- **事件追加**：`appendEvent` 有字节/数量上限（64KB/事件、1MB/run、MAX_SERVER_RUN_EVENTS），超限时丢弃最旧的「可滚动」事件（diagnostic/text/thinking/context-usage），保留 tool-request/tool-result/status/retry/终态。
- **SSE**：`sseForRun` 用 cursor 协议（`after` + `Last-Event-ID`）做可恢复事件流；单 run 最多 4 订阅、全局 32 订阅。
- **恢复**：`recoverServerRun` 从 sidecar 重建 run，合成被中断工具的 tool-result 闭包，补写终态 transport 事件；sessionGeneration 变化会驱逐旧 run。
- **结算**：`setRunStatus` 到终态（awaiting-user/completed/failed/cancelled）时 `appendTerminalEvents` 先拒绝 pending 工具、flush 持久化、再写 status/done 事件。

### 8. 模型与重试（model.ts / llm-retry.ts / executor-events.ts）

- `createServerLanguageModel`：provider 工厂（anthropic/gemini/kimi/qwen/deepseek/mistral/xai + openai-compatible），走本地 `/llm` 代理注入真实 key。
- `serverProviderOptions`：Anthropic cache control（short/long ephemeral）、OpenAI responses 模式 store:false、minimax reasoning_split。
- `resolveServerRunMaxOutputTokens`：取「请求值、能力上限、有效输出预算」三者的最小值。
- `collectServerText`：流式拆分 text/thinking 事件，2 秒定时 flush 短尾巴，避免浏览器重载丢文本。

## 关键架构约束（迁移到 Python 时需保留的语义）

1. **服务端不碰项目**：system prompt 里「服务端执行权威」明确服务端只拥有 LLM 循环、不拥有项目变更权（`context.ts` 第 66–71 行）。
2. **工具 = 命令**：每个工具最终落到 `EditorCommands` → `reducerActions.ts` 的 Action；迁移 Python 后端时，「工具面」与「命令/Action 层」的 1:1 契约必须保持（见 tools-surface.md）。
3. **canonical schema 校验**：服务端把浏览器提交的工具 schema 与打包的 JSON 目录逐名严格比对，防注入/篡改。
4. **capability 验证**：run 的所有后续请求（claim/result/events/cancel/settle）都需 `x-openchatcut-run-capability` 头，sha256 校验。
5. **审批轨迹**：工具请求/结果/审批/提案都持久化（approval 记录 + proposal 事件），支持服务重启恢复。

## Caveats / Not Found

- 本文聚焦 `server/agent-runs/`（服务端循环）。浏览器侧的完整审批 UI 流程在 `src/agent/` 的 `runtime-ledger.ts`（`AgentRunRecorder`）与 `src/editor/store.ts` 的 `makeDraft`（proposal draft engine）里，属前端/渲染面，未在本迁移范围。
- `codex-turn.ts` 的 Codex 后端通过 `server/plugins/codex-agent.ts` 与 `server/codex/turn-manager.ts` 衔接，本报告未展开读这两个文件（Codex 后端非 API 后端，且迁移范围未定）。
- 迁移到 Python(FastAPI) 后，Node 特有的 `ai`（Vercel AI SDK）`streamText`/`tool()` 与 SSE 实现需换成 Python 等价物；模型调用走本地 `/llm` 代理的模式是否保留取决于新后端是否继续承担代理职责。
