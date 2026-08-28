# 架构对齐 design

## 目标

把单体后端拆成原版的两端，**1:1 复刻 MCP 通信语义**（用户已确认：前端 TS 重写 reducer、纯 FFmpeg、mock 存根、1:1 MCP）。

```
browser（Vue3，权威）              server（Python）
┌──────────────────────────┐      ┌─────────────────────────────┐
│ EditorCore: ProjectDoc   │      │ LLM 决策循环（不持有权威）    │
│   projectReduce + 快照栈  │      │ MCP Streamable HTTP + broker │
│   buildCommands + draft  │      │ claim/settle 协议 + SSE       │
│ executeTool（tool==cmd）  │      │ 重插件（cd 已做）+ SQLite     │
└──────┬───────────────────┘      └──────────┬──────────────────┘
       │ claim/settle（内部 run）· broker 长轮询（外部 MCP）│
       └───────────────────────────────────────┘
```

## 1. 前端 EditorCore（TS，权威）

### 1.1 目录结构

```
frontend/src/
  editor/
    types.ts        # ProjectDoc/Timeline/TimelineItem/… 权威类型
    reduce.ts       # projectReduce 纯函数 + historyReduce 快照栈
    commands.ts     # buildCommands：命令 → action → dispatch
    draft.ts        # makeDraft 草稿引擎（记录 actions）
  agent/
    tools.ts        # executeTool：工具 1:1 映射命令
  bridge/
    serverRun.ts    # 内部 run 的 claim/settle 客户端（SSE + claim + settle）
    externalBridge.ts # 外部 MCP 的 broker 轮询客户端
```

### 1.2 规模：78 命令（以 Python 为可执行规格）+ 骨架先行

TS reducer 覆盖 **78 命令**（与 Python `commands/` 对齐）。Python 的 `Command.apply(state)->new_state` 是**可执行规格**，TS 重写 = 把 78 个命令逐条翻译成 `projectReduce(doc, action)` 的 action 分支。纯机械翻译，用 trellis-implement 子代理按 `domain/` 模块分批。

**骨架先行**分两批：

- **第一批（骨架命令，先做，~13 个）**：`add_clip` / `remove_clip` / `move_clip` / `duplicate_clip` / `split_clip` / `set_clip_timing` / `set_clip_transform` / `set_clip_volume` / `add_transition` / `undo` / `redo` / `read_timeline` / `read_project` —— 拖拽与 agent 编辑的核心，先立住「browser 单一真源 + 快照栈 + claim/settle」闭环。
- **第二批（低频命令，机械补，~65 个）**：字幕/转写（transcript 系列）、关键帧/滤镜/特效、多机位/联动组、项目级（多时间线/素材池/设计风格）等，对照 Python `commands/` 逐条翻译。

### 1.3 reducer 设计（对齐 reduce.ts 三层）

```ts
// historyReduce：快照栈
interface History { past: ProjectDoc[]; present: ProjectDoc; future: ProjectDoc[] }
const HISTORY_LIMIT = 100
// mutation action → past.push(oldPresent), present=next, future=[]
// 非 mutation action（select/switch）→ 只换 present，不进历史

// projectReduce(doc, action): ProjectDoc  纯函数，无副作用
// 非法操作返回原 doc（无效动作不进历史）
```

Vue3 落地：`reactive<History>` 持状态，`projectReduce` 是普通纯函数（不进 Vue 响应式系统，只有结果 `present` 进），`buildCommands` 产出的命令调用 `dispatch(action)`。

### 1.4 类型层（types.ts）

复用现有 `api.ts` 的类型（已含 ProjectDoc/Timeline/Clip/Marker/MediaAsset/…）作为权威类型基底，补上 Python domain 里前端还没对齐的字段（transform/keyframes/effects/reframeKeyframes/linkGroups/multicamGroups 等）。不另起炉灶。

### 1.5 草稿引擎（draft.ts）

```ts
makeDraft(base): DraftEngine {
  // 复用 projectReduce，操作草稿副本，记录 actions，不碰真库不进历史
  // { commands, getState, getDoc, takeActions }
}
replayActions(base, actions) // 应用到真库
```

## 2. Python 后端（server）

### 2.1 LLM 循环（从 loop.py 迁移）

现有 `app/agent/loop.py` 的 `run_agent` 迁移为 server 侧循环：**不再持有 Executor**，改为产出 tool-request 事件 + `waitForToolResult` 挂起，等 browser claim/settle。工具执行器（`executeTool`）移到 browser，server 只「选工具 + 传参」。

保留：autonomous acceptance 循环（mutation 后读复核）、无 turn 上限、`ToolEffect=read|reversible_edit|persistent_local|irreversible_external` 分类。

### 2.2 MCP Streamable HTTP server

用 Python 官方 `mcp` SDK（`pip install mcp`，等价 @modelcontextprotocol/sdk）的 `streamable_http` transport。端点 `/api/external-mcp/mcp`，`mcp-session-id` 头标识会话，bearer token 鉴权（`OPENCHATCUT_MCP_TOKEN`）。

OpenChatCut 自身即 MCP server；外部客户端（Claude/Codex）连入。

### 2.3 broker（长轮询 + 状态机）

`app/mcp/broker.py`，asyncio 实现：

```
queues: dict[projectId, list[QueuedCall]]
pending: dict[callId, QueuedCall]
waiters: 长轮询唤醒信号
```

状态机 `queued → in_flight → applied/stale/cancelled/rejected/failed`。deadline 180s（可至 600s）。browser 轮询 `nextEditorCall`（先 touchEditor 续租，再 takeNextCall，空则 waitForWake 长轮询 25s）。

### 2.4 registry（browser 注册）

`app/mcp/registry.py`：`registerEditor({projectId, editorId, baseRevision, tools})` → 返回 `registrationCapability`（43 位 base64url）作为后续 poll/result 鉴权头。revision 防漂移（baseRevision 不符则拒绝或 allowRevisionDrift）。

## 3. 两条链路协议

### 3.1 链路 A：内部 server run（claim/settle）

| 步骤 | 端 | 端点 |
|---|---|---|
| create run（延迟执行）| browser→server | `POST /api/agent-runs` |
| start run | browser→server | `POST /api/agent-runs/:id/start` |
| SSE 事件流 | server→browser | `GET /api/agent-runs/:id/events` |
| claim | browser→server | `POST /api/agent-runs/:id/tool-claim` |
| result | browser→server | `POST /api/agent-runs/:id/tool-result` |

server 侧 `waitForToolResult`（`app/agent_runs/store_tools.py`）：登记 `ServerToolRequest(status=pending)` + `claimId`/`argsDigest`/`outcomeDigest` 三重防护，超时 `SERVER_TOOL_RESULT_TIMEOUT_MS`。

### 3.2 链路 B：外部 MCP（broker 长轮询）

外部客户端 `call_tool` → MCP server `callTool` → `invokeEditorTool` 入 broker 队列 → browser `GET /api/external-agent/poll` 取 → draft 执行 → `POST /api/external-agent/result` 结算 → broker 唤醒 MCP session 返回结果。

### 3.3 edit-session 三段式（外部 MCP 用）

1. `begin_edit_session(clientName, approvalMode)` → `createExternalEditSession` 建 DraftEngine
2. 每个 editor 工具在 draft 上执行，记录 actions
3. `review_edit_session` → buildProposal → manual 弹 UI 确认 / auto 立即 apply → 原子落库

## 4. 关键语义必须等价（1:1）

- broker 状态机 + deadline 超时
- `registrationCapability` 鉴权 + `baseRevision` 防漂移
- `tool == command` 契约（schema 与 browser 同源）
- draft + proposal + apply 三段式（外部客户端从不直接写 ProjectDoc）
- 5 个 MCP 控制工具（openchatcut_status/list_projects/create_project/target_project/get_editor_url）不经 broker，server 直接处理

## 5. 实施顺序（阶段划分）

| 阶段 | 内容 | 依赖 |
|---|---|---|
| arch-1a | 前端 TS EditorCore 骨架：types + reduce + 快照栈 + draft + 13 骨架命令 | 无（对照 Python 翻译） |
| arch-1b | 前端 TS 剩余 ~65 低频命令（机械翻译） | arch-1a |
| arch-2 | Python MCP server + broker + registry | arch-1a 的类型契约 |
| arch-3 | 内部 run 的 claim/settle + SSE + LLM 循环迁移 | arch-1a + arch-2 |
| arch-4 | 端到端接线：外部 MCP 客户端 + edit-session 三段式 | 前三个 |

arch-1a 完成后，arch-1b（机械翻译）与 arch-2/3/4（协议）可并行推进：一边子代理补低频命令，一边搭 MCP 闭环。

## 6. 风险与回滚

- **TS 翻译工作量**：78 命令 + 类型 + reducer 分支。用「Python 可执行规格 + 分批子代理翻译 + 每批对照测试」控制风险；先翻 domain 类型，再翻 reduce，最后 commands。
- **MCP SDK 兼容**：Python `mcp` SDK 的 streamable_http 与 JS 版协议等价，若 SDK 版本差异导致协议不匹配，回退手动 JSON-RPC over HTTP。
- **单体→分离的状态迁移**：现有 `Executor`/`commands` 不删，降级为 offline 模式的 server-direct 路径（对齐原版 offline-runtime.ts），保证能力补齐（cd）不回退。
- 每阶段独立 commit，可回退。
