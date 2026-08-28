# 架构对齐：server/browser 分离 + MCP 通信层

## 背景

当前迁移版是单体 FastAPI 后端（持有 ProjectDoc + Executor + LLM loop），前端 Vue3 是 SSE 薄客户端。本子任务把它拆成原版 OpenChatCut 的两端，并 **1:1 复刻 MCP 通信协议语义**（用户已确认：不做简化协议）。

**为何必须 browser 权威（而非 server 权威）**：前端后续要支持**拖拽 + canvas 实时渲染**。拖拽是每秒几十次的连续写操作，reducer 必须在 browser 内存（本地即时反馈），否则每次 tick 都 round-trip 到 server 会卡顿。这决定了 agent 工具与用户拖拽必须共享同一个 browser reducer（单一真源、统一 undo/redo），否则会双写漂移、将来二次迁移。所以「工具留在后端」（= 原版 offline 模式）被否决。

研究基线：`research/arch-server-browser-split.md`、`mcp-broker.md`、`editor-core.md`。

## 目标架构（对齐原版）

```
┌────────────── browser（前端，持有权威）──────────────┐
│  ProjectDoc 唯一真源（projectReduce + 快照栈 undo）   │
│  executeTool → EditorCommands → reducer               │
│  draft 草稿引擎 + proposal/apply                     │
└──────────────┬───────────────────────────────────────┘
               │ claim/settle（内部 run）· broker 长轮询（外部 MCP）
┌──────────────▼────────────── server（Python 后端）────┐
│  LLM 决策循环（不持有 mutation authority）            │
│  MCP Streamable HTTP server + broker                  │
│  autonomous acceptance 循环                           │
│  重插件（FFmpeg/ASR/export，来自 cd 子任务）+ SQLite   │
└───────────────────────────────────────────────────────┘
```

## 需求

### 1. server / browser 职责分离

- **server 只跑 LLM 决策循环**，绝不直接改 ProjectDoc（对齐原版 `context.ts` 写死的「server owns the LLM loop, not mutation authority」）。
- **browser 持有 ProjectDoc 唯一真源**：`projectReduce` 纯函数 + 快照栈 undo/redo（`HISTORY_LIMIT=100`）+ `makeDraft` 草稿引擎。
- 前端从薄 SSE 客户端升级为持有 EditorCore（Vue3 版等价实现）。

### 2. 两条链路（原版并存，都要等价）

**链路 A：内部 server run（server 决策，browser 执行）**
- `/api/agent-runs` 的 `create`（延迟执行）+ `start`
- SSE 事件流 `/api/agent-runs/:runId/events`（`id:`/`event:`/`data:` 帧，支持 cursor 重放）
- claim/settle：`/tool-claim` + `/tool-result`，三重防护 `claimId` / `argsDigest` / `outcomeDigest`
- server 侧 `waitForToolResult` 挂起，等待 browser 结算

**链路 B：外部 MCP agent（外部客户端决策，browser 执行）**
- Streamable HTTP MCP server（OpenChatCut 自身即 MCP server）
- broker 长轮询（状态机 `queued → in_flight → applied/stale/cancelled/rejected/failed`）
- browser 注册上报工具（`/register`，含 `baseRevision` + 工具目录）
- edit-session 三段式：`begin_edit_session` → draft 上执行 → `review_edit_session` / apply
- 5 个 MCP 控制工具（`openchatcut_status` / `list_projects` / `create_project` / `target_project` / `get_editor_url`）不经 broker，server 直接处理

### 3. autonomous acceptance（验收循环）

- 无 turn 上限，靠「模型不再产 tool call」自然终止
- mutation 后强制注入 `<autonomous_acceptance iteration=N max=M>` 只读复核消息
- `read` 类工具（`read_project`/`read_timeline`/inspect/probe）在 checking 阶段推进 `verifiedAfterMutation`
- `checking && verifiedAfterMutation` → finish；超 `maxIterations` → fail

### 4. 关键语义必须等价（1:1，非简化）

- broker 状态机 `queued/in_flight/applied/stale/cancelled/rejected/failed` 及 deadline 超时（180s 可至 600s）
- `registrationCapability`（43 位 base64url）鉴权、`baseRevision` 防漂移
- `tool == command` 契约（工具 1:1 映射命令，schema 与 browser 同源）
- edit-session draft + proposal + apply 三段式（外部客户端从不直接写 ProjectDoc）

## 关键决策（已定）

- **browser 权威**：前端 TS 重实现 `projectReduce` + 快照栈 undo/redo + `makeDraft` 草稿引擎，成为 ProjectDoc 唯一真源。
- **Python 命令层降级为 offline 模式**（对齐原版 `offline-runtime.ts` 的 server-direct 路径），不删除，供「无 browser 连接」场景 + 测试参考。
- 为什么：见背景段——拖拽/canvas 实时交互要求 reducer 在 browser 内存，且 agent 工具与用户拖拽必须共享单一真源。

## 实施节奏（骨架先行）

先立住「browser 单一真源 + claim/settle + MCP broker」骨架（含**高频命令**），验证闭环跑通；剩余低频命令是纯机械翻译，用子代理分批补，不阻塞架构生效。

- **骨架命令**（第一批，先翻译）：添加/删除/移动片段、设置片段变换/音量/时长/源入点、撤销/重做、读时间线/读项目、切分片段、添加转场——这些是拖拽与 agent 编辑的核心。
- **低频命令**（第二批，机械补）：字幕/转写/关键帧/滤镜/多机位/联动组/项目级命令等，对照 Python `commands/` 逐条翻译。

## 验收标准

1. 外部 MCP 客户端（Claude/Codex）能经 Streamable HTTP 连入，调用编辑工具经 broker → browser draft 执行 → review/apply 落库，结果回传。
2. 内部 server run：browser 创建 run → server LLM 决策 → `/tool-claim`+`/tool-result` 结算 → autonomous acceptance 读复核后终止。
3. 前端 undo/redo 在快照栈上正确（HISTORY_LIMIT=100，mutation 进历史、非 mutation 不进）。
4. server 不直接改 ProjectDoc（代码审查可证）；edit-session draft 不污染真库直到 apply。
5. revision 防漂移：`baseRevision` 不符时 broker 拒绝或走 `allowRevisionDrift` 语义。
6. cd 子任务补齐的 FFmpeg/ASR/export 作为 server 端重插件，经工具调用可达（不与 browser 权威冲突）。
