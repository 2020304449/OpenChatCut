# implement：agent-runs 运行时健壮性

分 5 阶段，每阶段独立 commit、可回滚。工作目录 `learning/openchatcut-backend/`。

## 阶段 1：tool-policy + store-approval 后端

1. **新增 `backend/app/agent_runs/policy.py`**：`classify(name)` / `requires_approval(name)`，显式 high-risk 集合（见 design.md §1）。单元测试覆盖分类。
2. **改 `backend/app/agent_runs/store.py`**：`ServerToolRequest.status` 扩展 `pending_approval`/`approved`/`rejected`；加 `approve_tool_request(run, tool_call_id, decision)`（approved 唤醒 future 继续，rejected 唤醒并标记）。
3. **改 `backend/app/agent_runs/executor.py`**：遇到 `requires_approval(tool)` → `register_tool_request`（status=pending_approval）→ 产出 `approval_request` 事件 → `await_approval`；approved 后继续产出 `tool_request`，rejected 后跳过（记录 rejected 结果进 messages）。
4. **改 `backend/app/agent_runs/routes.py`**：加 `POST /api/agent-runs/{run_id}/approval`（body `{toolCallId, decision}`）。
5. **新增测试 `backend/tests/test_agent_runs_robustness.py`**：policy 分类、审批 approve/reject 全流程（用 MockLlm + 一个 high-risk 工具）。
6. **验证**：`cd backend && ./.venv/Scripts/python.exe -m pytest -q` 全绿（含现有 test_agent_runs）。

## 阶段 2：审批前端接线

1. **改 `frontend/src/bridge/serverRun.ts`**：`ServerRunHandlers` 加 `onApprovalRequest(name, args, decide)`；`streamServerRun` 处理 `approval_request` 事件，调 handler 并挂起等 `decide(decision)`，再 `POST .../approval`；`create` 请求体加 `supportedTools`（阶段 5 用，可先传空）。
2. **改 `frontend/src/App.vue`**：加审批弹框（confirm/模态），`onApprovalRequest` 里展示工具名+参数，用户 approve/reject 后 `decide`。
3. **验证**：`cd frontend && export PATH="/d/mise/data/installs/node/24.19.0:$PATH" && npx tsc --noEmit && npm test` 全绿。

## 阶段 3：acceptance-loop

1. **改 `backend/app/agent_runs/executor.py`**：把 `mutated/verified` 布尔改为 `verify_round` 计数；工具执行后追加验收指令；LLM 继续给 tool_calls 视为「未过、继续修正」，无 tool_calls 视为「通过、break」；验收轮次上限（如 3）强制 break。
2. **测试**：`test_agent_runs_robustness.py` 加 acceptance 用例（MockLlm 模拟「第一次修改 + 第二次无 tool_calls 验收通过」）。
3. **验证**：后端 pytest 全绿。

## 阶段 4：store-recovery + store-metrics

1. **改 `backend/app/agent_runs/store.py`**：`RunStore` 加 SQLite 持久化（复用 `app/storage/sqlite_store.py`）；`persist(run)` 在状态变更时落盘（数据部分，排除 future）；`load()` 恢复未完成 run；`ServerRun` 加 `metrics` dataclass。
2. **改 `backend/app/agent_runs/executor.py`**：循环里更新 metrics（iterations/tool_calls/errors/耗时）。
3. **改 `backend/app/agent_runs/routes.py`**：加 `GET /api/agent-runs/{id}` 返回 run 摘要 + metrics。
4. **测试**：`test_agent_runs_robustness.py` 加 recovery（save→load 恢复）与 metrics（跑完 run 后 metrics 字段非零）用例。
5. **验证**：后端 pytest 全绿。

## 阶段 5：store-capability

1. **改 `backend/app/agent_runs/routes.py`**：`CreateBody` 加 `supportedTools: list[str] | None`；存入 `ServerRun.supported_tools`。
2. **改 `backend/app/agent_runs/executor.py`**：`tools.schemas()` 按 `supported_tools` 裁剪（缺省全量）。
3. **改 `frontend/src/bridge/serverRun.ts`**：`create` 传 `supportedTools`（`SUPPORTED_TOOL_NAMES`）。
4. **测试**：capability 裁剪用例（传子集 → LLM 工具面只含子集）。
5. **验证**：后端 pytest + 前端 tsc/vitest 全绿。

## 收尾

1. 全量：后端 pytest + 前端 tsc/vitest 全绿。
2. 手跑：后端 `start.ps1` + 前端 `npm run dev`，触发一个生成工具（如「生成一张封面」）确认审批弹框出现、approve 后继续、reject 后跳过。
3. 确认现有 `/api/export`、外部 MCP、持久化链路不受影响。

## 回滚

- 每阶段独立 commit。阶段 1-5 各只动后端或前端单侧（阶段 2/5 涉及前端），互不牵连。
- 出问题 `git revert` 对应 commit。

## 关键验证命令（本机）

```bash
# 后端
cd learning/openchatcut-backend/backend && ./.venv/Scripts/python.exe -m pytest -q

# 前端
cd learning/openchatcut-backend/frontend && export PATH="/d/mise/data/installs/node/24.19.0:$PATH" && npx tsc --noEmit && npm test
```

## 非目标（别顺手做）

- tool-catalog-generation（`schemas()` 已实现）。
- server 端 offline 执行（browser 权威不变，read 类仍走 claim/settle）。
- 删除类工具的 action 级审批（多动作工具按名分类，删除暂不审批，靠 undo 兜底）。
- run 无缝续跑（恢复目标 = 状态不丢可审计，不自动续跑 LLM 循环）。
- token 精确计数（LLM 客户端不返回 usage）。
