# implement：external MCP 完整度（运行时 3 模块）

单阶段实现（3 模块集中在 mcp/，改动小），独立 commit 可回滚。工作目录 `learning/openchatcut-backend/`。

## 阶段 1：registry 持久化

1. **改 `backend/app/mcp/registry.py`**：`Registry.__init__(db_path=None)`；加 `_persist()` / `load()`；`register`/`unregister`/`update_revision` 后 `_persist()`；加 `list()`；`EditorRegistration` 序列化/反序列化（用 `dataclasses.asdict` / 手动构造）。
2. **改 `backend/app/mcp/server.py`**：模块级 `registry = Registry(db_path=os.path.join(data_dir(), "external-agent.sqlite3"))`。
3. **验证**：`cd backend && ./.venv/Scripts/python.exe -m pytest -q` 全绿（现有 test_external_agent/test_broker 不受影响）。

## 阶段 2：mcp-check + client-connect

1. **改 `backend/app/mcp/broker.py`**：加 `pending_count()` / `registered_projects()`。
2. **改 `backend/app/mcp/server.py`**：加 `mcp_check` MCP 工具；`openchatcut_status` 的 `connectedClients` 改真实值 `len(registry.list())`。
3. **改 `backend/app/mcp/routes.py`**：加 `GET /api/external-agent/connections` + `POST /api/external-agent/disconnect`。
4. **新增测试 `backend/tests/test_external_mcp_completeness.py`**：
   - registry 持久化：register → 新 Registry 同 db load → 恢复 editor。
   - `mcp_check`：无注册时 browserOnline=False；注册后 True。
   - connections/disconnect：register 后 connections 列表含该项目；disconnect 后为空。
5. **验证**：后端 pytest 全绿。

## 收尾

1. 后端 pytest 全绿（现有 + 新增）。
2. 确认现有 `/api/export`、agent-runs、持久化链路不受影响。

## 回滚

- 阶段 1/2 各自独立 commit，出问题 `git revert`。

## 关键验证命令（本机）

```bash
cd learning/openchatcut-backend/backend && ./.venv/Scripts/python.exe -m pytest -q
```

## 非目标（别顺手做）

- jianying-export（剪映草稿导出，后续）。
- import-token（凭证导入）。
- 生成类工具接真实服务（#1，后续融入新后端）。
