# agent-runs 运行时健壮性

## 目标与用户价值

当前 `agent_runs/` 是能跑通 claim/settle 的骨架（3 文件），但缺「运行时健壮性」：工具执行无策略/审批、agent 不验证自己的结果、run 状态不持久化、无遥测、无能力协商。本任务补齐这些，让 server 决策/browser 权威的 agent 循环在真实场景下更**可靠、安全、可观测、可自治验收**。

## 背景

- `agent_runs/` 现有 3 文件：`executor.py`（89 行）、`routes.py`（103 行）、`store.py`（107 行）。
- **store.py**：内存 `RunStore` + `ServerRun`/`ServerToolRequest`，claim/settle 三重防护（claimId / argsDigest / 幂等），无持久化、无审批态（`app/agent_runs/store.py`）。
- **executor.py**：`execute_run` 循环，有 `MAX_ITER=20`、`_compact`、简化 acceptance-loop（`mutated`/`verified` 标志）、LLM 调用 try/except（`app/agent_runs/executor.py:33-86`）。
- **routes.py**：create/start/SSE/claim/result（`app/agent_runs/routes.py`）。
- **agent/registry.py**：`schemas()` 已实现工具目录生成（`app/agent/registry.py:17-29`）。
- **mcp/registry.py**：`EditorRegistration.toolNames` 已有能力上报雏形（`app/mcp/registry.py:19,41`）。
- **mcp/broker.py**：已有完整状态机（queued/in_flight + 5 outcome + deadline），是外部 MCP 链路健壮性，**不在本任务范围**（`app/mcp/broker.py`）。
- **前端**：`bridge/serverRun.ts` 走 create/start/SSE/claim/settle，无审批交互（`frontend/src/bridge/serverRun.ts`）。

## 范围（补全 6 个模块）

| 模块 | 现状 | 本任务要做 |
|---|---|---|
| tool-policy | 无 | 工具分类 + 执行策略 |
| store-approval | 无 | 高风险工具挂起 + 前端人工 approve/reject |
| acceptance-loop | 简化版 | 执行→读状态→判断→失败重试闭环 |
| store-recovery | 无（内存） | run 持久化 + 重启恢复（可审计） |
| store-metrics | 无 | 迭代数/工具调用数/耗时/成功失败 |
| store-capability | mcp 雏形 | browser 声明工具集，server 裁剪工具面 |
| tool-catalog-generation | 已实现 | **无需补**（`schemas()`） |

## 关键决策

- **范围 = 全部 6 个缺失模块**（tool-catalog-generation 已存在，跳过）。
- **审批形态 = 人工审批（human-in-the-loop，前后端端到端）**：高风险工具停下，前端弹框，用户 approve/reject。
- **审批触发条件 = 生成类 + 导出类工具**（显式集合，见 design.md §1）：生成类 `submit_image/voice/sound/music/video/motion_graphic`、`create_motion_graphic_from_code`、`submit_shader`；导出类 `submit_export`、`submit_render_job`、`export_motion_graphic_prores`、`convert_motion_graphic_to_video`、`export_jianying_draft`。删除类**不审批**（有 undo 兜底，多动作工具按名分类无法精确到 action）。
- **browser 权威不变**：所有模块叠加在 claim/settle 之上，工具执行仍在浏览器，server 不引入 offline 执行。

## 验收标准

1. 后端 pytest 全绿：新增 policy/approval/acceptance/recovery/metrics/capability 测试。
2. 前端 tsc + vitest 全绿：审批接线（approval_request 事件 + 弹框 + approve/reject）。
3. 触发生成/导出工具（如「生成一张封面」）→ 前端弹审批框 → approve 继续执行 / reject 跳过该工具。
4. 工具执行后 agent 读状态自验，结果不符则继续修正，验收轮次达上限则强制结束（acceptance-loop）。
5. run 状态持久化到 SQLite，重启后可查询未完成 run（recovery）。
6. `GET /api/agent-runs/{id}` 返回 run 摘要含 metrics（迭代数/工具调用数/耗时）。
7. `create` 传 `supportedTools` 子集时，LLM 工具面被裁剪为子集（capability）。
8. 现有 `/api/export`、外部 MCP、项目持久化链路不受影响（现有测试仍绿）。

## 非目标

- tool-catalog-generation（已实现）。
- server 端 offline 执行（read 类仍走 claim/settle）。
- 删除类工具的 action 级审批（靠 undo 兜底）。
- run 无缝续跑（恢复目标 = 状态不丢可审计，不自动续跑 LLM 循环）。
- token 精确计数（LLM 客户端不返回 usage）。
