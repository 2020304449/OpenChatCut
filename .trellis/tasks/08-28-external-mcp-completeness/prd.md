# external MCP 完整度

## 目标与用户价值

当前 `mcp/` 是外部 MCP agent 接入的骨架（4 文件），已通 claim/settle 长轮询 + Streamable HTTP MCP server。本任务补齐外部 agent 的运行时能力：注册状态持久化（重启不丢）、连接健康检查、多客户端连接管理，让外部 agent 接入更健壮、可观测、可运维。

## 背景（已确认现状）

- `mcp/` 现有 4 文件：`broker.py`（124 行，长轮询状态机）、`registry.py`（61 行，browser 注册 + capability）、`routes.py`（106 行，register/poll/result）、`server.py`（97 行，MCP server + 5 控制工具）。
- **registry.py**：`Registry` 内存存储，`self._editors: dict[str, EditorRegistration]`（按 projectId 单 editor），无持久化（`app/mcp/registry.py:22-24`）。有 `register`/`get`/`unregister`/`verify`/`update_revision`。
- **server.py**：5 个控制工具（`openchatcut_status` 硬编码 `connectedClients: 1`，`app/mcp/server.py:60-83`），编辑工具经 broker 路由。
- **broker.py**：`queued/in_flight` 状态机 + deadline stale + 5 outcome（`app/mcp/broker.py`）。
- **routes.py**：register/poll/result 三个端点（`app/mcp/routes.py`）。

## 范围（已定：3 个运行时模块）

| 模块 | 现状 | 本任务要做 |
|---|---|---|
| agent-runtime-persistence | registry 内存 | `EditorRegistration` 持久化 SQLite + 重启恢复 |
| mcp-check | status 硬编码 | 真实连接健康检查（browser 是否在线 + 队列状态） |
| client-connect | 单 editor、无列表/断开端点 | 多客户端连接管理（列出/断开） |

## 需求（概要）

1. **agent-runtime-persistence**：`Registry` 加 SQLite 持久化（复用 `SqliteStore`），register/unregister/update_revision 时落盘，启动时 load 恢复。
2. **mcp-check**：加 `mcp_check` MCP 工具（或端点），返回真实连接状态（browser 是否注册、broker pending 数）。
3. **client-connect**：加 `list_connections` + `disconnect`（unregister）端点，支持多 projectId 多 editor 的连接生命周期管理。

## 关键决策（已定）

- **范围 = 3 个运行时模块**（jianying-export 和 import-token 列为后续/非目标）。

## 非目标

- jianying-export（剪映草稿导出，格式复杂，后续任务）。
- import-token（凭证导入，可用环境变量替代）。
- 生成类工具接真实服务（#1，后续融入新后端）。

## 验收标准

1. 后端 pytest 全绿（新增 registry 持久化 / mcp_check / connections / disconnect 测试）。
2. `register` 后新建 `Registry(db_path=同一 db)` 再 `load()` 能恢复 editor（持久化生效）。
3. `mcp_check` 返回真实状态：无注册时 `browserOnline=false`，注册后 `true`；`pendingCalls` 反映 broker 队列。
4. `GET /connections` 列出已注册项目；`POST /disconnect` 后列表为空。
5. 现有 `/api/export`、agent-runs、项目持久化、外部 MCP（register/poll/result）链路不受影响。
