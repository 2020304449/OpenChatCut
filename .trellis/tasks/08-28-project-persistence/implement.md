# implement：项目持久化端点

分两阶段，各独立可验收，可回滚。工作目录 `learning/openchatcut-backend/`。

## 阶段 1：后端路由 + lifespan（先做，独立可验收）

1. **新增 `backend/app/project_routes.py`**：`GET /api/project`（`load_project()` 无数据返回 `{"exists": false}`，有数据返回 `{"exists": true, "state": project_to_dict(doc)}`）；`PUT /api/project`（body `state: dict` → `project_from_dict` → `save_project`，异常返 400）。`save_project`/`load_project` **不带 path**，走 `OPENCHATCUT_DATA_DIR` 默认路径。
2. **改 `backend/app/main.py`**：加 `import os`、`from contextlib import asynccontextmanager`、`from .persist import data_dir`；加最小 lifespan（`os.makedirs(data_dir(), exist_ok=True)`）；`FastAPI(..., lifespan=lifespan)`；`app.include_router(project_router)`。
3. **新增 `backend/tests/test_project_routes.py`**：
   - `TestClient(app)` + `monkeypatch.setenv("OPENCHATCUT_DATA_DIR", str(tmp_path))`（参考 `tests/test_external_agent.py` 的 TestClient 用法 + `tests/test_sqlite.py` 的 env 隔离）。
   - 用例：① 首次 GET 返回 `{"exists": false}`；② PUT 一个 `project_to_dict(_make_doc())` 后 GET round-trip 一致（复用 `test_sqlite.py` 的 `_make_doc` 思路，或内联构造）；③ 重启模拟：PUT 后新 `TestClient`（或再 GET）仍能读到。
4. **验证**：`cd backend && ./.venv/Scripts/python.exe -m pytest -q` 全绿；`grep -rn "save_project\|load_project" app` 能看到 `project_routes.py` 引用。

## 阶段 2：前端 reset + hydration + 自动保存

1. **`src/editor/store.ts`**：`EditorStore` 接口加 `reset: (doc: ProjectDoc) => void`；`useEditor` 里 `reset(doc)` → `h.value = initHistory(doc)`；返回值加 `reset`。
2. **新增 `src/bridge/project.ts`**：`loadProject()`（GET，`{exists:false}` 或非 200 返 null）、`saveProject(doc)`（PUT `{ state: doc }`）。
3. **`src/App.vue`**：引入 `onMounted`、`watch`；`useEditor` 解构加 `reset`；加 `hydrated = ref(false)`；`onMounted` 里 `loadProject()` 成功且非空则 `reset(saved)`，`finally` 置 `hydrated = true`；`watch(doc)` 门控 `hydrated` + 500ms 防抖 `saveProject`（失败 `console.warn`）。
4. **新增 `src/editor/store.test.ts`**：`reset` 后 `doc` 等于新快照、`canUndo`/`canRedo` 为 false（undo 历史被清空）。
5. **验证**：`cd frontend && export PATH="/d/mise/data/installs/node/24.19.0:$PATH" && npx tsc --noEmit && npm test` 全绿。

## 阶段 3：全量验证 + 收尾

1. 后端 pytest + 前端 tsc/vitest 全绿。
2. 手跑：后端 `start.ps1` + 前端 `npm run dev`，编辑时间线 → 刷新页面 → 确认 `doc` 保持（Network 面板可见 `GET/PUT /api/project`；`data/project-store.sqlite3` 生成）。
3. 确认 `/api/export`、`/api/agent-runs`、外部 MCP 链路不受影响（现有测试仍绿）。

## 回滚

- 阶段 1 只动后端 + 后端测试；阶段 2 只动前端。各自独立 commit。
- 阶段 1 出问题 `git revert`；前端未接线时后端路由无副作用（仅多了未调用的端点）。

## 关键验证命令（本机）

```bash
# 后端
cd learning/openchatcut-backend/backend && ./.venv/Scripts/python.exe -m pytest -q

# 前端
cd learning/openchatcut-backend/frontend && export PATH="/d/mise/data/installs/node/24.19.0:$PATH" && npx tsc --noEmit && npm test
```

## 非目标（别顺手做）

- 多项目 / 项目列表 / 新建切换（单 `project:default`）。
- 版本号 / baseRevision 冲突检测（单用户 last-write-wins）。
- 媒体文件上传落盘（`/media/*` 仍是前端 public 静态资源，只存 src 字符串）。
- undo 历史持久化（只存 `present`）。
- 保存失败重试 / 离线队列 / 保存状态 UI（纯自动保存无按钮）。
