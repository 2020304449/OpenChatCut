# Research: server/browser 分离架构 + server/agent-runs LLM 循环

- **Query**: 原版 OpenChatCut 的「server 决策 / browser 权威」分离架构；server/agent-runs/ 的 LLM 循环入口、工具定义来源、tool call 决策、循环终止/验收机制；端到端命令流；关键架构决策。
- **Scope**: internal
- **Date**: 2026-08-28

## 一、server/agent-runs/ 的 LLM 循环（问题 1）

### 1.1 入口文件与 HTTP 挂载

- 入口插件：`server/agent-runs/routes.ts` → `agentRunsPlugin()`（routes.ts:523-545）把中间件挂在 `/api/agent-runs`。
- 路由分发表：`routeAgentRunRequest()`（routes.ts:472-493）：
  - `POST /` → `handleCreate`（routes.ts:193）创建 run 并**延迟执行**（`deferRunExecution` routes.ts:57，60s 入场超时）。
  - `POST /:runId/start` → `handleStart`（routes.ts:260）真正启动 `executeRun`。
  - `GET /:runId/events` → SSE 事件流（`handleEvents` → `sseForRun`，sse.ts:116）。
  - `POST /:runId/tool-claim` / `tool-result` / `cancel` / `settle` / `draft` / `draft/clear`：browser 端回传工具结果/结算。
  - `GET /:runId` → run 元数据。

> **确定事实**：run 的创建与启动被拆成两个 HTTP 调用（`deferredRuns` Map + `startDeferredRun`，routes.ts:57-77），browser 先 create 拿到 capability，再 start 触发执行。

### 1.2 循环主体

- `executeRun()`（`server/agent-runs/executor.ts:402`）→ `executeRunTurns()`（executor.ts:268-379）。
- 循环体是一个**无上限的 for 循环**（`for (let turn = 0; ; turn += 1)`），注释明确（executor.ts:276-278）：

```
// No turn cap: the model decides when the task is done. The only automatic
// stop beside "no more tool calls" is an output-token cutoff, ...
```

- 每轮二选一：
  - API 后端：`executeServerTurn` → `runServerTurnOnce`（executor.ts:137），用 Vercel AI SDK 的 `streamText`（executor.ts:155）+ `createServerTools`。
  - Codex 后端：`executeServerCodexTurn`（`server/agent-runs/codex-turn.ts:141`），走 `runServerCodexTurn`（`server/plugins/codex-agent.ts`）。

### 1.3 工具定义从哪来

三层来源，最终收敛到一份**构建期生成的 JSON catalog**：

1. 权威定义在 `src/agent/tools.ts` 的 `TOOL_SCHEMAS`（tools.ts:79-207）与 `src/agent/ask-mode-tools.ts` 的 `ASK_MODE_TOOL_SCHEMAS`。
2. `server/agent-runs/generate-tool-catalog.mts` 在构建期把它们序列化写入 `assets/agent/openchatcut-tool-schemas.json`（`{version:1, edit:[...], ask:[...]}`）。
3. 运行时 `server/agent-runs/tool-policy.ts` 从该 JSON 读回：
   - `canonicalServerRunToolCatalog(askOnly)`（tool-policy.ts:74）→ 不可变 canonical schema（`Object.freeze`）。
   - `resolveServerRunToolCatalog(requested, askOnly)`（tool-policy.ts:82）把 browser 在创建 run 时上报的工具列表**逐一校验**（`sameSchema` 逐字比对 name/description/input_schema），非 canonical 直接抛错。

> **确定事实**：`createServerTools()`（`server/agent-runs/browser-tool.ts:98-113`）把每个 `AgentToolSchema` 转成 AI SDK 的 `tool({ description, inputSchema: jsonSchema(...), execute, toModelOutput })`。**工具定义不在 server 硬编码**，而是从 browser 同源的 `TOOL_SCHEMAS` 生成、再通过 JSON 快照注入 server，保证 server 决策面与 browser 执行面 schema 一致。

### 1.4 tool call 决策如何产出

- `streamText` 产出 `toolCalls`；每个 tool 的 `execute` 回调（browser-tool.ts:108）调用 `executeBrowserTool(run, schema, args, options.toolCallId, activation)`。
- `executeBrowserTool`（browser-tool.ts:42-96）：
  - 串行化：非 `parallel` 工具走 `activation.tail` Promise 链（browser-tool.ts:49-56），保证顺序执行。
  - `ToolActivation.admit(name)` 激活工具（渐进式暴露）。
  - `assertCanonicalToolInvocation`（tool-policy.ts:106）校验参数 + 活跃目录。
  - `pushRunEvent(run, 'tool-request', { toolCallId, name, args, argsDigest })` 发事件。
  - **关键**：`waitForToolResult(run, toolCallId, schema.name, argsDigest)`（browser-tool.ts:75）—— 挂起一个 Promise，等待 browser 通过 HTTP 结算。

### 1.5 工具结果如何回传（server ↔ browser 的 claim/settle 协议）

- server 侧 `waitForToolResult`（`server/agent-runs/store-tools.ts:65-103`）在 `run.toolRequests` Map 里登记 `ServerToolRequest`（status:'pending'），带超时（`SERVER_TOOL_RESULT_TIMEOUT_MS`）。
- browser 侧 `ServerRunToolExecutor`（`src/agent/serverRunToolExecutor.ts`）：
  - `claim()`（serverRunToolExecutor.ts:130）POST `/api/agent-runs/:runId/tool-claim`（routes.ts:295 `handleToolClaim` → `claimToolRequest` store-tools.ts:105）。
  - 执行完 `postResult()`（serverRunToolExecutor.ts:165）POST `/api/agent-runs/:runId/tool-result`（routes.ts:307 `handleToolResult` → `settleToolResult` store-tools.ts:180）。
  - `deliverToolSettlement`（store-tools.ts:152-178）最终 `request.resolve(input.result)` 唤醒 server 挂起的 `waitForToolResult`。
- 三重防护：`claimId`（claim 归属）、`argsDigest`（参数一致性）、`outcomeDigest`（结算幂等）。

### 1.6 循环如何终止 + 验收机制

- `turnDisposition`（`server/agent-runs/acceptance-loop.ts:90-98`）返回 `'continue' | 'completed' | 'failed' | 'max-tokens'`。
- `continued` 判定（executor.ts:178-180）：`toolCalls.length > 0 || responseMessages.some(m => m.role === 'tool')`，否则 `completed`。
- 当 `completed` 时进入**自主验收循环** `decideAcceptanceAfterTurn`（acceptance-loop.ts:59-81）：
  - 状态机 `AcceptanceLoopState { enabled, maxIterations, phase: 'working'|'checking', iteration, mutated, verifiedAfterMutation }`。
  - 若本轮有 mutation 且尚未验证 → 注入一条 `<autonomous_acceptance iteration=N max=M>` 的 user 消息（acceptance-loop.ts:45-57），要求模型用 `read_project`/`read_timeline`/inspect/probe 工具复核「最后的编辑」。
  - `recordAcceptedTool`（acceptance-loop.ts:32-43）：`effect==='read'` 且处于 checking 阶段且之前 mutated → `verifiedAfterMutation=true`。
  - 判定：`checking && verifiedAfterMutation` → `finish`（passed）；`iteration >= maxIterations` → `fail`；否则 `continue` 注入验收消息。
- 验收是否启用由 `autonomousAcceptance`（`ServerRunInput.autonomousAcceptance`，executor.ts:80）+ `run.askOnly` 共同决定（executor.ts:233-236 `createAcceptanceLoop(input.autonomousAcceptance && !run.askOnly, ...)`）。
- 工具效果分类在 `src/agent/execution-policy.ts` 的 `policyForTool`（execution-policy.ts:80-98），`ToolEffect` = `read | reversible_edit | persistent_local | irreversible_external`（execution-policy.ts:7-11）。`read` 工具在 checking 阶段会推进验收。

> **确定事实**：循环的「自然终止」= 模型不再产 tool call；「验收」= mutation 后强制一次只读复核（acceptance loop），通过才算 completed，否则达到迭代上限即 fail。

### 1.7 SSE 事件流

- `server/agent-runs/sse.ts`：`sseForRun`（sse.ts:116）用 `text/event-stream` + `id:`/`event:`/`data:` 帧（sse.ts:55-62）。支持 `Last-Event-ID` / `after` cursor 重放（`resolveCursor` sse.ts:38）。订阅上限 4/run、32 全局（sse.ts:9-10）。`event.type==='done'` 或 run 终态即关流。

---

## 二、端到端命令流（问题 4）

原版有**两条并存链路**：

### 链路 A：内部 server run（server 决策，browser 执行）

| 步骤 | 进程 | 文件 |
|---|---|---|
| 用户发消息，browser 组装 messages + 上报工具目录 | renderer | `src/agent/serverRunSend.ts` 等 |
| POST `/api/agent-runs`（create）→ start | renderer→node | `routes.ts:193/260` |
| server LLM 循环 `streamText` 产 tool call | node | `executor.ts:268/137` |
| `executeBrowserTool` 挂起 `waitForToolResult` | node | `browser-tool.ts:42`、`store-tools.ts:65` |
| browser 长轮询 SSE 看到 `tool-request`，`ServerRunToolExecutor.handle` → `claim`（POST tool-claim） | renderer | `serverRunToolExecutor.ts:478/130` |
| browser `executeCodexTool` 在 **draft（makeDraft 草稿）** 上执行工具 → 记录 actions | renderer | `serverRunToolExecutor.ts:349-413`、`runtime.ts:224` |
| `postResult`（POST tool-result）回传结果 | renderer | `serverRunToolExecutor.ts:165` |
| server 继续循环 / 验收 | node | `executor.ts:329-377` |
| 终端：browser 侧 proposal → 用户确认 → `applyDoc`/`applyState` 落真库 | renderer | `src/agent/useAgentRun.ts`（`commitPersistentOperations` useAgentRun.ts:93，`applyDoc` useAgentRun.ts:121） |

> **推断**：server run 的「browser 执行」也走 **draft 草稿 + 事后 apply**，而不是直接 mutate 真库；server 只产出「工具名+参数」，真正的 ProjectDoc 变更由 browser 的 reducer 完成并记录成 actions，最后以 proposal 形式 apply。

### 链路 B：外部 MCP agent（Claude/Codex 决策，browser 执行）

| 步骤 | 进程 | 文件 |
|---|---|---|
| 外部客户端 call_tool | 外部进程 | — |
| OpenChatCut MCP server 收 CallToolRequest | node | `mcp.ts:273` |
| `callTool` → `invokeEditorTool` 入 broker 队列 | node | `mcp.ts:174`、`broker.ts:350` |
| browser 长轮询 `GET /api/external-agent/poll` 取 call | renderer | `external-agent-bridge-routes.ts:190`、`useExternalAgentBridge.ts:157` |
| `ExternalBridgeRuntime.execute` → 在 edit-session draft 上执行 | renderer | `external-bridge-runtime.ts:94` |
| `POST /api/external-agent/result` 结算 | renderer | `external-bridge-registration.ts:31`、`broker.ts:500` |
| broker 唤醒 MCP session 返回结果 | node | `broker.ts:150` |

---

## 三、关键架构决策（问题 5）

### 3.1 为什么 browser 持有权威而不是 server（确定事实，代码明示）

`server/agent-runs/context.ts:66-71` 在 system prompt 里写死了这一原则：

```
# Server execution authority
- The server owns the language-model loop, but it does not own project mutation authority.
- Browser tool requests must execute through the existing executeCodexTool/draft/EditorCommands path.
- Never edit ProjectDoc, files, media, or external systems directly from the server.
```

根本原因（事实支撑）：
1. **编辑器状态唯一真源是 reducer + ProjectDoc**（`src/editor/store.ts` 的 `useEditor` + `historyReduce`），undo/redo/命令/UI 全部围绕 browser 内存里的 `ProjectDoc` 展开。server 若要持有权威就得在 Node 里重实现整套 reducer/undo/redo，与 UI 状态必然双写、漂移。
2. **工具执行器天然在 browser**：`executeTool`（`src/agent/tools.ts:300`）按工具名懒加载 50+ 组 executor，最终落到 `EditorCommands`（`buildCommands`）→ reducer。server 只做「选工具 + 传参」的决策。

### 3.2 server 与 browser 各自持久化了什么状态（确定事实）

- **server 持久化（SQLite）**：`server/plugins/project-store.ts` → `server/storage/sqlite-store.ts`（`sqliteStoreEnabled()` 分支）。这是**多项目文档的耐久存储**（`project:${id}`、`projects` 索引、agent runtime sidecar、export recovery 等）。`list_projects`/`create_project`（`server/external-agent/projects.ts:53/60`）直接读写它。
- **server 内存态（不持久，进程内）**：run store（`store.ts:82` 的 `runs` Map，镜像到共享 KV）；MCP session 表（`mcp.ts:77` `sessions` Map）；broker 队列/registry（`broker.ts:61-66`）。
- **browser 持久化**：`src/persist/projectStore.ts` —— 注释明示「Server-backed multi-project store with an IndexedDB cache」（projectStore.ts 头部），即 **server SQLite 是权威、browser 有 IndexedDB 缓存**（`src/persist/sharedKv.ts` 的 `DB_NAME='openchatcut'` IndexedDB 后端）。
- **browser 权威编辑态**：`ProjectDoc` 内存 reducer（不落盘，落盘的是最终文档快照）。

> **关键区分**：server 有**项目文档的耐久存储（SQLite）**，但**没有编辑态（undo/redo/reducer/选区）**；browser 有**编辑态唯一真源**，但把**耐久存储委托给 server**。两者通过 `projectStoreTransport`（`src/persist/projectStoreTransport.ts`）+ HTTP（`server/project-store-http-routes.ts`）交互。

### 3.3 对「前后端分离」迁移的启示（推断 + 事实）

- **前端必须从薄客户端升级为持有 EditorCore**：迁移目标里「前端持有 EditorCore 真源」不是可选项。原版的 `useEditor`/`historyReduce`/`buildCommands`/`projectReduce`/`executeTool` 整套就是权威层，Vue3 前端需要等价实现（或复用逻辑）才能承接「browser 权威」角色。
- **后端职责收敛为三块**：① LLM 决策循环（对应 `server/agent-runs/executor.ts`）；② MCP 通信层 + broker（对应 `server/external-agent/`，见 `mcp-broker.md`）；③ 重插件（FFmpeg/ASR/export/媒体探测）与耐久项目存储（SQLite）。
- **两条协议必须保留**：server run 的 claim/settle HTTP 协议（`/api/agent-runs/:id/tool-claim`+`tool-result`）与 MCP 的 Streamable HTTP + browser 长轮询 broker。迁移到 Python 后端时，browser 长轮询的 broker 语义（queued/in_flight/applied/stale/cancelled）需要等价实现。
- **验收/一致性机制要保留**：autonomous acceptance（读复核）、revision/baseRevision 防漂移（`revisionOf` external-edit-session.ts:69 的 FNV-1a 哈希）、edit-session draft + proposal + apply 三段式。

---

## Caveats / Not Found

- 未逐字通读 `src/agent/serverRunSend.ts` / `serverRunProtocol.ts` 的 browser 侧 create/start 发送细节；结论基于 routes.ts 与 serverRunToolExecutor.ts 的协议对称推断。
- 「server run 工具执行走 draft 再 apply」的落库时机（proposal 确认 vs 自动 apply）依据 `useAgentRun.ts` 的 `commitPersistentOperations` 推断，未追踪 `useAgent.ts` 完整 UI 触发链。
- `server/storage/sqlite-store.ts` 的 schema 细节未展开；仅确认「SQLite 耐久存储」这一层级事实。
