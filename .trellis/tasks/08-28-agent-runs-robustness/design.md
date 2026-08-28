# design：agent-runs 运行时健壮性

## 0. 架构总览

内部 run 数据流（现状 + 本任务增量）：

```
前端 App.vue → create + start → execute_run 循环（server）
  ├─ LLM 产出 tool_calls
  ├─ [本任务] policy 判定：read / edit / high-risk
  │     ├─ high-risk → 产出 approval_request → 前端弹框 → approve/reject
  │     └─ 其余 → 产出 tool_request → 前端 claim → executeTool → settle
  ├─ [本任务] acceptance-loop：工具执行后 agent 读状态自验，失败则重试
  └─ [本任务] metrics 记录 + recovery 持久化
```

关键边界：**browser 权威不变**——工具执行仍在浏览器（`executeTool`），server 只「选工具 + 传参 + 策略/审批」。所有新模块叠加在 claim/settle 之上，不引入 server 端 offline 执行。

## 1. tool-policy（工具策略）

新增 `app/agent_runs/policy.py`，定义工具分类 + 执行策略。

**分类规则**（按工具名）：

| 分类 | 判定 | 策略 |
|---|---|---|
| `read` | `read_*` 前缀（read_timeline/read_project/read_transcript） | 走 claim/settle，无需审批 |
| `edit` | 其余编辑工具 | 走 claim/settle，无需审批 |
| `high-risk` | 生成/导出类（显式集合） | claim/settle 前**需审批** |

**high-risk 集合**（显式列出，可配置）：
- 生成类：`submit_image`、`submit_voice`、`submit_sound`、`submit_music`、`submit_video`、`submit_motion_graphic`、`create_motion_graphic_from_code`、`submit_shader`
- 导出类：`submit_export`、`submit_render_job`、`export_motion_graphic_prores`、`convert_motion_graphic_to_video`、`export_jianying_draft`

> 删除类（remove_clip/clear_timeline/delete_text 及 edit_*/manage_* 内嵌删除）**不审批**——有前端 undo 栈兜底，且多动作工具按名分类无法精确到 action，首版不引入 action 级审批。

`policy.py` 提供 `classify(name) -> "read" | "edit" | "high-risk"` 和 `requires_approval(name) -> bool`。生成类工具的 `kind` 可从 `generation_tools.GENERATION_TOOL_NAMES` 派生，但 policy 用显式集合（生成类里 `transcribe_track`/`probe_media` 是服务/只读，不算 high-risk）。

## 2. store-approval（审批流）

**状态机扩展**（`store.py` 的 `ServerToolRequest.status`）：

```
pending → pending_approval → approved → claimed → settled
                        ↘ rejected（终止）
```

**数据流**：

1. `executor` 遇到 `requires_approval(tool)` → `register_tool_request`（status=`pending_approval`）→ 产出 `approval_request` 事件 → `await_approval(req)` 挂起
2. 前端收到 `approval_request` → 弹框 → 用户 approve/reject → `POST /api/agent-runs/{id}/approval`（body: `{toolCallId, decision: "approved"|"rejected"}`）
3. 后端 `approve_tool_request`：approved → status=`approved` → 唤醒挂起 → 继续走 claim/settle（产出 tool_request）；rejected → status=`rejected` → 唤醒，executor 跳过该工具（记录 `{ok:false, rejected:true}` 进对话）

**前端接线**（`bridge/serverRun.ts` + `App.vue`）：
- `streamServerRun` 新增 `approval_request` 事件分支，调 `handlers.onApprovalRequest(name, args)` 并挂起等用户决定
- `App.vue` 新增审批弹框（简单 confirm/模态），用户决定后回调 `approve/reject` 到 server

**端点**：`store.py` 加 `approve_tool_request(run, tool_call_id, decision)`；`routes.py` 加 `POST /api/agent-runs/{run_id}/approval`。

## 3. acceptance-loop（自治验收）

改造 `executor.py` 的简化 `verified` 标志为真实闭环：

```
工具执行完 → 追加一条「验收指令」→ LLM 下一轮：
  ├─ 无 tool_calls 且已 mutate → 视为「验收通过」，break
  ├─ 有 tool_calls → 继续修正（新一轮）
  └─ 验收轮次超限（如 3 轮）→ 强制 break 并报 warning
```

具体：把当前 `mutated/verified` 布尔改为 `verify_round` 计数。工具执行后若未验收，追加 user message 让 LLM「调用 read_timeline 核对结果，若不符合意图则继续修正，否则总结」；LLM 若继续给 tool_calls 则视为「验收未过，继续修正」，计数 +1；无 tool_calls 则 break。验收轮次超限则 break（不无限循环）。

> 本质：让「验证 → 失败重试」由 LLM 决策驱动，而非固定标志。`read_timeline` 已在 47 编辑工具中，无需新增工具。

## 4. store-recovery（故障恢复）

`RunStore` 从纯内存 dict 改为「内存运行时 + SQLite 持久化」双层：

- **持久化**：`ServerRun` 的「数据部分」序列化到 SQLite（复用 `SqliteStore`，key 如 `run:{id}`）。序列化字段：id、message、initial_state、state、tool_requests 的静态字段（name/args/status/result）。
- **不可序列化**：`ServerToolRequest.future`（asyncio.Future）不落盘；恢复时重建，未完成的 request 标记为 `failed`（`{"ok":false,"error":"recovered after restart"}`）。
- **恢复**：服务启动（lifespan）或 `RunStore` 首次访问时，从 SQLite load 未完成的 run（state ∈ {pending, running}），供查询/审计；**不自动续跑**（run 的 LLM 循环依赖前端 SSE 订阅，重启后无人订阅，续跑无意义）——恢复的目标是「状态不丢、可审计」，不是「无缝续跑」。

`store.py` 加 `RunStore.persist(run)` / `RunStore.load()`；`run` 的每次状态变更（create/claim/settle/done）触发 persist。

## 5. store-metrics（遥测）

`ServerRun` 加 `metrics` 字段（dataclass）：

```python
@dataclass
class RunMetrics:
    iterations: int = 0          # LLM 迭代轮数
    tool_calls: int = 0          # 工具调用总次数
    approvals: int = 0           # 审批次数（approved/rejected）
    errors: int = 0              # LLM/工具错误次数
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    duration_ms: int | None = None
```

`executor` 循环里更新；`routes.py` 加 `GET /api/agent-runs/{id}` 返回 run 摘要（含 metrics）。不引入 token 精确计数（LLM 客户端当前不返回 usage），只记迭代/调用/耗时。

## 6. store-capability（能力协商）

- 前端 `create` 时携带 `supportedTools`（`SUPPORTED_TOOL_NAMES`，前端 `agent/tools.ts` 已导出）。
- 后端 `create` 存 `ServerRun.supported_tools`；`executor` 生成 LLM 工具面时，用 `supported_tools` 裁剪 `build_registry().schemas()`（只给 browser 支持的工具）。
- 缺省（未传）时给全量工具面（向后兼容）。

`routes.py` 的 `CreateBody` 加 `supportedTools: list[str] | None = None`；`executor` 的 `tools.schemas()` 改为裁剪后输出。

## 7. 数据流契约汇总

新增/变更的 SSE 事件与端点：

| 类型 | 事件/端点 | 说明 |
|---|---|---|
| SSE 新增 | `approval_request` | high-risk 工具审批请求 |
| 端点新增 | `POST /api/agent-runs/{id}/approval` | 审批决定（approved/rejected） |
| 端点新增 | `GET /api/agent-runs/{id}` | run 摘要 + metrics |
| create 扩展 | `supportedTools` | 能力协商字段 |

## 8. 关键文件改动清单

- 后端新增：`app/agent_runs/policy.py`（工具策略）
- 后端改：`app/agent_runs/store.py`（审批态 + 持久化 + metrics）
- 后端改：`app/agent_runs/executor.py`（acceptance-loop + policy 分流 + metrics）
- 后端改：`app/agent_runs/routes.py`（approval 端点 + run 摘要端点 + supportedTools）
- 前端改：`src/bridge/serverRun.ts`（approval_request 事件 + 能力协商字段）
- 前端改：`src/App.vue`（审批弹框）
- 后端新增测试：`tests/test_agent_runs_robustness.py`（policy/approval/acceptance/recovery/metrics/capability）
- 前端测试：`src/editor/store.test.ts` 或新文件（审批接线逻辑）

## 9. 兼容与回滚

- 所有新能力**叠加**在 claim/settle 上，缺省行为不变（无 supportedTools → 全量工具面；无审批 → 现状）。现有 `test_agent_runs.py`、`test_external_agent.py` 应保持绿。
- 分阶段 commit（见 implement.md），每阶段独立回滚。
