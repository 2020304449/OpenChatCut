# design：前端接线 + 后端清理

## 1. 前端接线：App.vue 从薄客户端 → browser 权威

### 1.1 状态持有

`App.vue` 用 `useEditor(defaultProject())`（`editor/store.ts`）持有 `History`（快照栈唯一真源）。组件不再从 `props.project` 读，改从 `useEditor` 的 `doc`（`ComputedRef<ProjectDoc>`）读。

### 1.2 聊天数据流（内部 run）

```
ChatPanel 输入 → createAndStartRun(message, doc, executeTool, ctx, handlers)
                    │  ctx = { getDoc: () => doc.value, commands: editor.commands }
                    │  ① POST /api/agent-runs (create)
                    │  ② POST /api/agent-runs/:id/start
                    │  ③ GET  /api/agent-runs/:id/events (SSE)
                    │      tool_request → claim → executeTool → settle
                    ▼
                onState → 刷新 doc / onAssistant → 流式文本
```

**简化决策**：内部 run 的 `ctx` 直接用**真库 store**（`editor.commands`），不是 draft。工具执行直接落在 `useEditor` 上，undo/redo 由快照栈兜底。理由：内部 run 是用户在主界面发起的对话，用户盯着 UI，无需 draft 隔离 + proposal 确认（那是外部 MCP 无 UI 确认时的机制）。draft + proposal 的完整流程留后续。

`executeTool` 来自 `agent/tools.ts`；`createAndStartRun`/`streamServerRun` 来自 `bridge/serverRun.ts`（已写好）。

### 1.3 undo/redo

`App.vue` 的撤销/重做按钮改调 `editor.commands.undo()/redo()`（本地 reducer），删掉 `api.ts` 的 `undo/redo` HTTP 客户端。

### 1.4 api.ts 处置

- 删 `streamChat`/`getState`/`undo`/`redo`。
- 删 `api.ts` 里的旧传输类型（`Clip`/`Timeline`/`ProjectDoc`/...）——全部改从 `editor/types.ts` 导入。
- `api.ts` 里 `parseSse` 逻辑 `bridge/serverRun.ts` 已有等价实现，`api.ts` 整体可删（或仅留无引用的空壳待后续删除）。

## 2. 后端删除

### 2.1 删（旧薄客户端 HTTP 路径 + 老循环）

| 位置 | 删什么 |
|---|---|
| `main.py` | `/api/chat`、`/api/state`、`/api/undo`、`/api/redo`、`/api/tools` 端点；模块级 `executor = Executor(...)`；`lifespan` 里的 `load_project`/`save_project(executor.state)`；`run_agent`/`Executor`/`default_project` 等旧 import |
| `agent/loop.py` | `run_agent`（老 LLM 循环）——**但保留** `build_system_prompt` + `_compact` + `_estimate_tokens`（被 `agent_runs/executor.py` 复用） |

### 2.2 保留（offline 底座 + schema 源）

| 位置 | 保留原因 |
|---|---|
| `commands/*.py` + `Executor` | offline 降级底座（80 命令 `apply` 纯规格）；`generation_tools.py` 的 mock 仍在 `ctx.executor.execute` 写状态 |
| `agent/tools.py` 的 46 个 `exec_*` + `Tool.execute` + `ToolContext` + `TOOLS` | offline 执行体 + schema 源（给 `agent_runs` 和 MCP 提供工具面） |
| `agent/registry.py` 的 `build_registry()` + `schemas()` + `execute` | `build_registry()`/`schemas()` 给 `agent_runs/executor.py` 提供 LLM 工具面；`execute` 是 offline 底座调度/参数校验入口，被 `test_tools`/`test_multicam`/`test_generation_mock` 锁定（并非「仅 `run_agent` 调用」），保留 |
| `agent/loop.py` 的 `build_system_prompt`/`_compact` | `agent_runs/executor.py` 复用 |
| `agent/generation_tools.py` | 20 个生成/导出工具，server 端重插件（mock），offline 底座 |
| `domain/*`、`mcp/*`、`agent_runs/*`、`persist`、`storage/*`、`services/*`、`llm.py` | 新架构 + 耐久存储底座 |

### 2.3 注意：persist 暂时无入口

删掉 `main.py` lifespan 的 load/save 后，`persist.py`（SQLite KV）会暂时无调用方——它是「后续 browser→server 项目持久化端点」的底座，保留但暂不接线（与 offline 底座同理，半死但被测试锁着）。

## 3. 工具双写一致性校验

后端 `tools.py` 的 `TOOLS`（46 编辑 + 20 生成）与前端 `tools.ts` 的 `executeTool`（46 编辑 case + read + 生成走 default）是两份「认知」。本任务落地一个**前端单源清单**兜底：

- `agent/tools.ts` 导出一个 `SUPPORTED_TOOL_NAMES: readonly string[]`（executeTool 实现的编辑工具名集合，不含生成工具）。
- 前端 vitest 断言 `SUPPORTED_TOOL_NAMES` 里每个名字调用 `executeTool` 都**不返回** `not implemented`。
- 新增编辑工具时：改后端 `TOOLS` + `exec_*`，同时改前端 `SUPPORTED_TOOL_NAMES` + `executeTool` case；漏同步 → vitest 红。

真正的跨语言自动比对（后端 TOOLS 名字 ↔ 前端清单）留到「schema 单源化」优化，本任务不做 build 快照。

## 4. 关键文件改动清单

- 前端改：`App.vue`、`api.ts`（删/重写）、`components/TimelineView.vue`、`components/AssetPanel.vue`、`components/ChatPanel.vue`、`components/ToolCallLog.vue`、`agent/tools.ts`（加 `SUPPORTED_TOOL_NAMES`）、`agent/tools.test.ts`（加一致性测试）。
- 后端改：`main.py`、`agent/loop.py`（删 `run_agent`）、`tests/`（删或改引用 `/api/chat` 等旧端点的测试）。`agent/registry.py` **不动**（`execute` 保留，见 2.2）。
