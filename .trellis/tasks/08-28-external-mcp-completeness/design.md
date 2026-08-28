# design：external MCP 完整度（运行时 3 模块）

## 1. agent-runtime-persistence（Registry 持久化）

`Registry`（`app/mcp/registry.py`）加 SQLite 持久化，复用 `SqliteStore`。

- `Registry.__init__(db_path: str | None = None)`：`db_path` 为 None 时行为不变（测试/无持久化场景）。
- 持久化单元：整个 registry 状态（`_epoch` + `_editors` 字典）序列化为一个 JSON，存 `registry:state` 单 key。
- 触发点：`register` / `unregister` / `update_revision` 后 `_persist()`。
- `load()`：启动时（或首次访问）从 SQLite 恢复 `_epoch` + `_editors`。
- `server.py` 的模块级 `registry = Registry()` 改为 `Registry(db_path=os.path.join(data_dir(), "external-agent.sqlite3"))`。

序列化格式：
```json
{
  "epoch": 3,
  "editors": {
    "default": {"projectId":"default","editorInstanceId":"e1","baseRevision":"r0",
                "capability":"...","ownershipEpoch":3,"toolNames":["add_clip"]}
  }
}
```

## 2. mcp-check（连接健康检查）

- `Broker` 加 `pending_count() -> int`（返回 `len(self._pending)`）和 `registered_projects()`（返回 `list(self._queues.keys())`）。
- `server.py` 加 MCP 工具 `mcp_check`，返回真实状态：
  ```python
  {"ok": True, "browserOnline": registry.get("default") is not None,
   "pendingCalls": broker.pending_count(), "registeredProjects": registry.list()}
  ```
- 替换 `openchatcut_status` 的硬编码 `connectedClients: 1` 为真实值（`len(registry.list())`）。

## 3. client-connect（多客户端连接管理）

- `Registry` 加 `list() -> list[EditorRegistration]`（返回所有注册）。
- `routes.py` 加两个运维端点：
  - `GET /api/external-agent/connections`：返回所有注册（projectId/editorInstanceId/ownershipEpoch/toolNames 摘要）。
  - `POST /api/external-agent/disconnect`：body `{projectId}` → `registry.unregister(projectId)`，返回 `{"ok": True}`。
- 多 projectId 多 editor 天然支持（registry 按 projectId 分桶），无需改 broker。

## 4. 数据流契约汇总

| 类型 | 端点/工具 | 说明 |
|---|---|---|
| MCP 工具新增 | `mcp_check` | 连接健康检查 |
| 端点新增 | `GET /api/external-agent/connections` | 列出连接 |
| 端点新增 | `POST /api/external-agent/disconnect` | 断开连接 |
| registry 改造 | 持久化 + `list()` | 重启恢复 + 列表 |

## 5. 关键文件改动清单

- 后端改：`app/mcp/registry.py`（持久化 + list）
- 后端改：`app/mcp/broker.py`（`pending_count`/`registered_projects`）
- 后端改：`app/mcp/server.py`（`mcp_check` 工具 + status 真实值 + registry db_path）
- 后端改：`app/mcp/routes.py`（connections/disconnect 端点）
- 后端新增测试：`tests/test_external_mcp_completeness.py`

## 6. 兼容与回滚

- 所有新能力叠加，缺省行为不变（db_path=None 时 registry 仍内存）。
- 现有 `test_external_agent.py`、`test_broker.py` 应保持绿。
