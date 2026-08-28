# Research: server/external-agent/ 的 MCP broker（问题 2）

- **Query**: 原版 OpenChatCut 的 MCP broker 完整协议（JSON-RPC? SSE? stdio?）、谁启动 MCP server、browser 端暴露哪些工具、server 端 agent 如何调用、双向通信数据结构。
- **Scope**: internal
- **Date**: 2026-08-28

## 一、协议选型：Streamable HTTP MCP，不是 stdio / SSE

- OpenChatCut **自己就是 MCP server**，用官方 SDK `@modelcontextprotocol/sdk` 的 **`StreamableHTTPServerTransport`**（`server/external-agent/mcp.ts:5` 导入，mcp.ts:409 实例化）。
- MCP 端点挂在 `/api/external-mcp/mcp`（`server/plugins/external-agent.ts:139-148`），由 Vite 中间件 `externalAgentPlugin()`（external-agent.ts:130）处理。
- 会话用 HTTP 头 `mcp-session-id` 标识（mcp.ts:367 `sessionIdOf`），无该头则 `startMcpSession`（mcp.ts:402）新建 transport 会话。
- MCP capability 声明（mcp.ts:255）：`capabilities: { tools: { listChanged: true }, prompts: {} }`。
- 鉴权：`externalMcpAuthorized`（`server/editor-auth.ts`，external-agent.ts:140）校验 bearer token（`OPENCHATCUT_MCP_TOKEN`）。

> **确定事实**：是 **JSON-RPC over Streamable HTTP**（MCP 标准 transport），不是本地 stdio、也不是裸 SSE。SSE 只出现在「server run 的事件流」（`/api/agent-runs/:id/events`）里，那是另一套协议，与本 MCP 层无关。

## 二、谁启动 MCP server

- **OpenChatCut 自身启动**（作为 Electron 的 Vite dev/prod 中间件），不 spawn 子进程。
- 反向地，`connectExternalClient`（`server/external-agent/client-connect.ts:148-178`）把 OpenChatCut 的 MCP 端点 + bearer token **写入外部客户端的配置文件**，让 Claude/Codex/Cursor 连过来：
  - Claude：`~/.claude.json` 的 `mcpServers.openchatcut = { type:'http', url, headers:{Authorization: Bearer <token>} }`（client-connect.ts:75-77, 167）。
  - Cursor：`~/.cursor/mcp.json`；Antigravity：`~/.gemini/antigravity/mcp_config.json`（client-connect.ts:168-172）。
  - Codex CLI：`codex mcp add openchatcut --url ... --bearer-token-env-var OPENCHATCUT_MCP_TOKEN`（client-connect.ts:94），并写 `~/.zshrc` 导出 token。
- 触发入口：`POST /api/external-agent/connect-client`（external-agent.ts:115-125）。

## 三、browser 端暴露哪些工具

### 3.1 工具目录来源与组装

- browser 端 `externalToolSchemas()`（`src/agent/external-tool-schemas.ts:28-35`）：
  ```
  [...globalReadTools, ...EXTERNAL_SESSION_TOOLS, ...editorTools, ...realTools]
  ```
  - `externalGlobalReadSchemas`：只读全局读工具（`isExternalGlobalReadTool`）。
  - `EXTERNAL_SESSION_TOOLS`（`src/agent/external-tool-shape.ts:24-74`）：4 个生命周期工具 —— `begin_edit_session` / `get_edit_session` / `review_edit_session` / `discard_edit_session`。
  - `externalDraftSchemas`（external-tool-shape.ts:95）：**编辑草稿工具**，每个注入必填 `editSessionId`（`withSession` external-tool-shape.ts:76）。
  - `externalRealSchemas`（external-tool-shape.ts:117）：真实工程工具（generation/export/import 等），每次调用需一次性确认。
- 这些工具最终都来自 `src/agent/tools.ts` 的 `TOOL_SCHEMAS`（50+ 组，tools.ts:79-207），用 `isExternalDraftTool`/`isExternalRealTool`/`isExternalGlobalReadTool`（`src/agent/external-tool-policy.ts`）过滤。

### 3.2 server 端补充的控制工具

- `MCP_CONTROL_TOOLS`（`server/external-agent/mcp-controls.ts:3-57`）：`openchatcut_status` / `list_projects` / `create_project` / `target_project` / `get_editor_url`。这些**不经 broker**，由 server 直接处理（`callControlTool` mcp.ts:135）。
- 完整 MCP 工具面 = 控制工具 + 注册的 browser 工具（`fullMcpTools` mcp.ts:84-105），并给每个 browser 工具注入 `editorProjectId`（`PROJECT_SELECTOR` mcp.ts:63）。

### 3.3 注册流程（browser 上报工具）

- `registerEditorBridge`（`src/agent/external-bridge-registration.ts:64-103`）POST `/api/external-agent/register`，body 含 `{ projectId, editorId, baseRevision, tools: externalToolSchemas() }`。
- server 侧 `registerBridgeEditor`（`server/plugins/external-agent-bridge-routes.ts:118-166`）→ `claimBrowserProjectOwnership`（project-edit-ownership）→ `registerEditor`（broker.ts:220 → broker-registry.ts:89）。
- 返回 `{ ok, ownershipEpoch, registrationCapability }`，browser 保存 `registrationCapability`（43 位 base64url 随机串，作为后续 poll/result 的鉴权头 `X-OpenChatCut-Editor-Registration`）。

## 四、server 端 agent 如何调用 + broker 队列

### 4.1 调用链

`handleMcpRequest`（mcp.ts:476）→ `makeServer`（mcp.ts:252）注册 `CallToolRequestSchema` handler（mcp.ts:273）→ `callTool`（mcp.ts:174）→ 对非控制工具走 `invokeEditorTool`（broker.ts:350）。

### 4.2 broker 本质：进程内队列 + 长轮询（确定事实）

`server/external-agent/broker.ts` 维护（broker.ts:61-66）：
- `queues: Map<projectId, QueuedCall[]>` —— 每个项目的待派发调用队列。
- `pending: Map<callId, QueuedCall>` —— 在途调用（含 resolve/reject）。
- `waiters` —— 长轮询唤醒信号；`cancellationQueues`/`cancellationWaiters` —— 取消队列。

`invokeEditorTool`（broker.ts:350-391）：
- 校验 edit-session 归属（`requireOwnedEditSession` broker.ts:309）与 binding 新鲜度（`requireCurrentBinding` broker.ts:321，区分 `allowRevisionDrift`/`allowAdopt`）。
- 入队 `QueuedCall { id, ownerId, binding, name, arguments, state:'queued', allowRevisionDrift, deadline, resolve, reject, timer }`，设 180s（可至 600s）超时。
- `wake(waiters, projectId)` 唤醒 browser 长轮询。

`nextEditorCall`（broker.ts:422-469）：
- browser 轮询时先 `touchEditor` 续租（online lease），再 `takeNextCall`（broker.ts:393）取队首、检查 deadline 与 binding（stale 过滤）、置 `in_flight`。
- 若空则 `waitForWake` 长轮询（`EDITOR_POLL_BUDGET_MS=25s`，`EDITOR_POLL_REFRESH_MS=8s`，broker.ts:56-58）。

`settleEditorCall`（broker.ts:500-515）→ `finishCall`（broker.ts:150-169）：
- 校验 `registrationCapability` 匹配，`pending.delete`，`clearTimeout`，`wake(waiters)`。
- outcome `'applied'` → `recordEditSessionOwner`（记 `begin_edit_session` 返回的 editSessionId 归属）+ `resolve(value)`。
- 其他 outcome → `enqueueCancellation`（若 in_flight 需通知 editor）+ `reject(ExternalEditorCallError)`。

### 4.3 双向通信数据结构（broker-types.ts）

```ts
// ExternalToolSchema（broker-types.ts:1）
{ name, description?, annotations?{readOnlyHint,destructiveHint,idempotentHint,openWorldHint}, input_schema{type:'object',...} }

// EditorBinding（broker-types.ts:18）
{ projectId, editorInstanceId, baseRevision, ownershipEpoch? }

// ExternalCallTerminalOutcome（broker-types.ts:25）
'applied' | 'rejected' | 'cancelled' | 'stale' | 'failed'

// ExternalEditorCall（broker.ts:40）
{ id, name, arguments, binding }

// ExternalEditorCancellation（broker.ts:47）
{ id, outcome(排除 applied), message, ownerGone?: string[] }
```

### 4.4 browser 侧轮询与执行（链路闭环）

- `useExternalAgentBridge`（`src/agent/useExternalAgentBridge.ts:468`）在 `useExternalPolling`（:380）里 `runBridge`（:282）→ `runBridgeAttempt`（:241）：
  1. `registerEditorBridge`（注册 + 拿到 ownership）。
  2. 并发两个轮询：`pollEditor`（:157，GET `/poll`）与 `pollCancellations`（:194，GET `/cancellation`）。
  3. 收到 call → `executeExternalCall`（:116）→ `ExternalBridgeRuntime.execute`（`src/agent/external-bridge-runtime.ts:94`）。
  4. `sendEditorBridgeResult`（external-bridge-registration.ts:31，POST `/result`）结算。
- 执行结果先过 `projectExternalReply`（useExternalAgentBridge.ts:80）做 artifact 序列化阈值检查，再 `flushProjectSaves`（useExternalAgentBridge.ts:140）刷盘，最后带 `baseRevision` 结算，使 broker registry 同步到 post-tool revision（external-agent-bridge-routes.ts:269-279）。

## 五、edit-session 语义（确定事实）

外部编辑采用**草稿三段式**（`src/agent/external-edit-session.ts`）：
1. `begin_edit_session`（clientName, approvalMode: manual|auto）→ `createExternalEditSession`（external-edit-session.ts:95）基于当前 `baseDoc` 建 `DraftEngine`（`makeDraft`，store.ts:71）。
2. 每个 editor 工具在 **draft 草稿**上执行并记录 actions（`captureExternalToolActions` external-edit-session.ts:183）。
3. `review_edit_session`（external-edit-session.ts:196）→ `buildProposal`（`src/agent/proposal.ts`）→ `awaiting_review`；manual 模式在 OpenChatCut UI 弹确认卡，auto 模式立即 apply（`external-bridge-runtime.ts:341-350`）。
4. `ExternalBridgeRuntime.apply`（external-bridge-runtime.ts:234）→ `commitExternalProposal`（`src/agent/external-proposal-apply.ts`）原子提交到真库。

> **确定事实**：外部 MCP 客户端从不直接写 ProjectDoc，永远在 edit-session draft 上编辑，最后 review/apply 原子落库；manual 模式把「确认」交给 OpenChatCut UI。

## 六、offline 回退（无 browser 时）

- `targetMcpProject`（`server/external-agent/mcp-binding.ts:126-153`）：若目标项目没有 connected browser，则创建 `OfflineExternalEditRuntime`（`server/external-agent/offline-runtime.ts:57`）。
- offline 模式 **server 直接执行**（`executeOfflineTool`，`offline-runtime.ts:17`），要求 `approvalMode="auto"`（offline-runtime.ts:191-195），server 直接对 SQLite 项目文档做 draft/commit（`commitReviewedDraft` offline-runtime.ts:339 → `persistence.commitProject`）。
- `mcpStatus`（mcp.ts:119-133）把 `bindingMode`（browser/offline）与 `availableToolTier`（browser/server-direct）回报给客户端。

## 相关 Spec / 文件索引

- `server/plugins/external-agent.ts` —— MCP 端点 + bridge 端点挂载。
- `server/plugins/external-agent-bridge-routes.ts` —— browser bridge HTTP 路由（register/unregister/poll/cancellation/result/tools）。
- `server/external-agent/broker-registry.ts` —— 连接注册表（ownership/revision/capability/online lease）。
- `server/external-agent/project-edit-ownership.ts` —— 项目编辑所有权（epoch）。
- `src/agent/useExternalAgentBridge.ts` / `external-bridge-runtime.ts` —— browser 侧桥。

## Caveats / Not Found

- `offline-executor.ts` 的 `executeOfflineTool` 具体工具白名单与 server-direct 能力边界未逐条展开（只确认了存在性与 `assertOfflineToolAllowed` 授权门）。
- `@modelcontextprotocol/sdk` 的确切版本号未查证（未读 package.json 依赖版本）。
- MCP `prompts`（`registerMcpPrompts` mcp.ts:272）的具体内容未展开。
