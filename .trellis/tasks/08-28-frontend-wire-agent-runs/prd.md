# 前端接线 agent-runs 路径 + 后端清理老执行体

## 背景

arch 子任务已把「server 决策 / browser 权威」架构搭好：前端 `editor/`（reducer 权威）、`bridge/`（两条链路客户端）、`agent/tools.ts`（executeTool）都写完且测试绿；后端 `/api/agent-runs/*`（内部 run）+ `/api/external-agent/*` + `/api/external-mcp/*`（外部 MCP）也都通了。

但**前端 App.vue 还是薄 SSE 客户端**，走老单体路径 `/api/chat`（server 端 `run_agent` 直接持有 Executor 执行工具），导致后端**两套执行路径并存**：

```
旧（前端在用）： App.vue → /api/chat → run_agent → tools.execute → exec_* → Executor.execute(Command)
新（已搭好未接）： App.vue → bridge/serverRun → /api/agent-runs/* → SSE → claim/settle → 前端 executeTool → useEditor reducer
```

本任务把前端正式切到新路径，并删除后端的旧薄客户端执行体。

## 目标

1. **前端成为真正的 browser 权威**：App.vue 用 `useEditor` 持有 ProjectDoc 唯一真源，聊天走 `bridge/serverRun.ts`（create → start → SSE → claim → executeTool → settle），不再依赖 `/api/chat`/`/api/state`/`/api/undo`/`/api/redo`。
2. **后端删旧执行体**：删掉 `/api/chat` 等旧 REST 端点 + `run_agent`，把 server 从「两套执行路径」收敛为「agent-runs + external MCP + offline 底座」。

## 范围

### 前端（切到新路径）

- `App.vue`：改为 `useEditor(defaultProject())` 持有状态；消息发送走 `createAndStartRun`（bridge/serverRun.ts）；undo/redo 用 `useEditor` 的 `commands.undo/redo`（本地 reducer，不再请求 `/api/undo`）。
- `api.ts`：删掉 `streamChat`/`getState`/`undo`/`redo`（旧端点客户端）；保留 `parseSse` 逻辑迁到 bridge 层复用。类型改从 `editor/types.ts` 导入（`api.ts` 的旧传输类型可整删，由 `editor/types.ts` 权威类型取代）。
- 组件（`TimelineView`/`AssetPanel`/`ChatPanel`/`ToolCallLog`）：从 `api.ts` 类型改为 `editor/types.ts` 类型；数据源从 `props.project` 改为 `useEditor` 的 `doc`。
- 本任务**不做**拖拽/canvas（那是下一个任务），只把只读视图的数据源从旧 API 切到权威 store。

### 后端（删旧执行体）

**删：**
- `main.py` 的 `/api/chat`、`/api/state`、`/api/undo`、`/api/redo`、`/api/tools` 端点 + 模块级 `executor = Executor(...)` + lifespan 里 `load_project/save_project(executor.state)`。
- `agent/loop.py` 的 `run_agent`（老 LLM 循环）。

**保留（offline 底座 + schema 源）：**
- `agent/loop.py` 的 `build_system_prompt` + `_compact`（被 `agent_runs/executor.py` 复用）。
- `commands/*.py` + `Executor`（offline 降级底座，且 `generation_tools.py` 的 mock 仍在 `ctx.executor.execute` 写状态）。
- `agent/tools.py` 的 46 个 `exec_*` + `Tool.execute` + `ToolContext`（offline 降级的 server 版 executeTool + schema 源）。
- `agent/registry.py` 的 `build_registry()` + `schemas()` + `execute`（`execute` 是 offline 底座的调度/参数校验入口，被 `test_tools`/`test_multicam`/`test_generation_mock` 锁定——并非「仅 `run_agent` 调用」，故保留）。
- `domain/*`、`mcp/*`、`agent_runs/*`、`persist`、`storage/*`、`services/*`。

## 关键决策

- **offline 降级路径保留**：`commands/` + `Executor` + `exec_*` 按原设计「Python 命令层降级为 offline 模式，不删除」，作为后续 offline-runtime（external MCP 无 browser 时 server 直接执行）的底座。本任务**不接线 offline-runtime**，只删「旧薄客户端 HTTP 路径」。
- **`/api/tools` 端点删除**：调试用端点，其信息已被 MCP `tools/list` 覆盖，删。
- **工具双写是 offline 的结构性代价**：一个编辑工具的执行语义同时存在于后端 `exec_*`（offline 执行体）与前端 `executeTool`（browser 权威执行体），新增工具要两处同步。原版 OpenChatCut 同样如此（browser `executeTool` vs offline `executeOfflineTool`）。缓解办法是「两端都从同一份 Python `commands/*.py` 可执行规格推导 + 测试对照」，本任务加一条**工具清单一致性校验**兜底（见验收标准 6）。
- **schema 暂不单源化**：当前 schema 只定义在后端 `args_model`（前端不独立维护 schema，无第三份双写）。「browser 单源 → build 快照 → server 读」的 schema 单源化是后续优化，不在本任务范围。

## 验收标准

1. 前端发消息走 `/api/agent-runs`（create → start → SSE），不再请求 `/api/chat`；`getState`/`undo`/`redo` 的前端 HTTP 调用消失，undo/redo 走本地 reducer。
2. 后端删掉旧端点后，`run_agent` 不再存在；`ToolRegistry.execute` 保留（offline 底座调度入口，被工具测试锁定）；`build_system_prompt`/`build_registry().schemas()` 仍被 `agent_runs` 正常引用。
3. 后端 pytest 全绿（删旧端点后无残留引用报错）；前端 tsc + vitest 全绿。
4. 前端只读视图数据源已切到 `editor/types.ts` 权威类型 + `useEditor`（不再 import 旧 `api.ts` 类型）。
5. 现有两条链路（内部 run、外部 MCP）测试仍通过，证明清理没破坏新架构。
6. **工具清单一致性**：后端 `TOOLS`（46 个编辑工具）的名字集合 == 前端 `executeTool` 覆盖的 case 集合；新增编辑工具漏同步会被测试抓住（生成类 20 个工具除外，它们走 server 端）。

## 非目标

- 拖拽/canvas 视频轨道（下一个任务）。
- offline-runtime 接线（后续任务）。
- 删除 `commands/`/`Executor`/`exec_*`（保留为 offline 底座）。
