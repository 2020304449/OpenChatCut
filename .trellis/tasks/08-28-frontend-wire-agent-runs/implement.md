# implement：前端接线 + 后端清理

分三阶段，每阶段独立 commit，可回滚。工作目录 `learning/openchatcut-backend/`。

## 阶段 1：后端删旧执行路径（先做，独立可验收）

1. **`app/main.py`**：删 `/api/chat`、`/api/state`、`/api/undo`、`/api/redo`、`/api/tools` 五个端点；删模块级 `executor = Executor(...)`；删 `lifespan` 里的 `load_project`/`save_project(executor.state)`（lifespan 整体可删）；删 `run_agent`/`Executor`/`default_project`/`project_to_dict`/`create_llm` 等仅旧路径用的 import。保留 `agent_runs_router`、`external_agent_router`、`external_mcp_app` 挂载 + CORS。
2. **`app/agent/loop.py`**：删 `run_agent` 函数及其 `ToolContext`/`ToolRegistry` import。**保留** `build_system_prompt`、`_compact`、`_estimate_tokens`（`agent_runs/executor.py` 依赖前两者）。
3. **`app/agent/registry.py`**：**不动**。`ToolRegistry.execute` 不是「仅 `run_agent` 调用」——`test_tools.py`/`test_multicam.py`/`test_generation_mock.py`（约 20 个测试）都经 `build_registry().execute(...)` 验证 offline 底座。删它会破坏步骤 4 里「不动」的测试，故与 `persist.py` 一样作为「被测试锁着的 offline 底座」保留。
4. **改测试**：
   - `tests/test_loop.py`：整删（`run_agent` 的语义已被 `tests/test_agent_runs.py` 的 `execute_run` async 版覆盖）。
   - `tests/test_engineering.py`：删 `test_run_agent_mock_full_flow`；保留 `_compact`/`_estimate_tokens` 的测试。
   - 其余 `test_commands/extra_commands/multicam/transcript/tools/generation_mock/sqlite.py` 都测 `Executor`/`commands`（offline 底座），**不动**。
5. **验证**：`cd backend && ./.venv/Scripts/python.exe -m pytest -q` 全绿；`grep -rn "run_agent\|/api/chat" app tests` 无残留引用。

## 阶段 2：前端切新路径

1. **`src/App.vue`**：
   - `useEditor(defaultProject())` 持有状态；`const { doc, commands, canUndo, canRedo } = useEditor(...)`。
   - 消息发送改调 `createAndStartRun(message, doc.value, executeTool, ctx, handlers)`，`ctx = { getDoc: () => doc.value, commands }`，`handlers.onState` 更新视图（`doc` 是 `ComputedRef`，自动响应）。
   - undo/redo 按钮改调 `commands.undo()/redo()`，删 `undoApi`/`redoApi` import。
2. **`src/api.ts`**：删 `streamChat`/`getState`/`undo`/`redo` + 全部旧传输类型。组件类型改从 `editor/types.ts` 导入。若 `api.ts` 无剩余引用则整删。
3. **组件**（`TimelineView`/`AssetPanel`/`ChatPanel`/`ToolCallLog`）：`props.project` 改为从 `useEditor` 注入的 `doc`（或父组件传 `doc.value`）；import 从 `../api` 改 `../editor/types`。
4. **`src/agent/tools.ts`**：导出 `SUPPORTED_TOOL_NAMES: readonly string[]`（executeTool 实现的编辑工具名集合，46 个编辑工具 + 3 个 read 工具，不含生成工具）。
5. **验证**：`cd frontend && export PATH="/d/mise/data/installs/node/24.19.0:$PATH" && npx tsc --noEmit && npm test` 全绿；`grep -rn "from '../api'\|from './api'" src` 无残留旧类型 import。

## 阶段 3：工具一致性校验 + 收尾

1. **`src/agent/tools.test.ts`** 追加一致性测试：断言 `SUPPORTED_TOOL_NAMES` 里每个名字调用 `executeTool(name, {}, ctx)` 的结果**不含** `error: 'tool not implemented'`（用最小 ctx；允许返回 `item not found` 等业务错误，只要不是 not implemented）。
2. 人工对照 `backend/app/agent/tools.py` 的 `TOOLS` 清单，确认编辑工具名与 `SUPPORTED_TOOL_NAMES` 一一对应（生成类 20 个除外）。
3. **全量验证**：后端 pytest + 前端 tsc/vitest 全绿；手跑 `npm run dev` + 后端 `start.ps1`，确认聊天走 `/api/agent-runs`（Network 面板无 `/api/chat` 请求）、undo/redo 走本地 reducer、时间线视图正常渲染。

## 回滚

- 每阶段独立 commit；阶段 1 只动后端 + 后端测试，阶段 2 只动前端，互不牵连。
- 若阶段 1 出问题：`git revert` 该 commit，旧 `/api/chat` 路径立即恢复。

## 关键验证命令（本机）

```bash
# 后端
cd learning/openchatcut-backend/backend && ./.venv/Scripts/python.exe -m pytest -q

# 前端
cd learning/openchatcut-backend/frontend && export PATH="/d/mise/data/installs/node/24.19.0:$PATH" && npx tsc --noEmit && npm test
```

## 非目标（别顺手做）

- 拖拽/canvas 视频轨道（下一任务）。
- offline-runtime 接线（后续任务，`commands`/`Executor`/`exec_*` 保留为底座）。
- schema 单源化 build 快照（后续优化）。
