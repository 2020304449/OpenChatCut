# 项目持久化端点（browser↔server）

## 目标与用户价值

工程数据目前只存在于前端内存里（`App.vue` 的 `useEditor(demoProject())`），关闭浏览器即丢失。本任务把 `persist.py`（SQLite KV 文档库）重新接回运行入口，补上「browser 权威 state → server 落盘 → 重启加载」的 HTTP 端点，让工程数据关掉浏览器后能恢复。

用户价值：**编辑成果不再因刷新/关页丢失**。

## 背景

- `persist.py` 底座已完整：`save_project(doc)` / `load_project()`（含 JSON→SQLite 迁移）/ `data_dir()` / `default_path()` / `project_from_dict()`（`app/persist.py:63-128`）；存储后端 `SqliteStore` 是 `kv(k,v)` JSON 文档库（`app/storage/sqlite_store.py:12-59`）。
- `main.py` 无 lifespan、无 project 路由，只挂 `agent-runs` + `export` + `external-agent` + `external-mcp`（`app/main.py:22-30`）。`persist.py` 的 `save_project/load_project` 目前**零 HTTP 调用方**（上轮任务 `design.md` §2.3 明确「保留但暂不接线」）。
- 前端 `App.vue` 用 `useEditor(demoProject())` 持有状态，纯内存（`frontend/src/App.vue:13`）。
- `useEditor` 只暴露 `dispatch(Action)`，**无「整体替换 doc」入口**——从后端加载工程需要新增 reset/replace 能力（`frontend/src/editor/store.ts:17-33`）。
- `demoProject()` 是含真实媒体 src 的演示工程（`frontend/src/editor/demo.ts:5-45`）。
- 架构是 **browser 权威**：前端把完整 `ProjectDoc`（dict）POST/PUT 给 server，server 还原后落盘。已有先例：`/api/export` 收完整 `state`（`app/export_routes.py:25-30`）；`/api/agent-runs` create 收 `state`（`app/agent_runs/routes.py:26-28`）。
- 单项目：`PROJECT_KEY = "project:default"`（`app/persist.py:18`）；MCP 也是单 `default` 项目。多项目是后续（`app/mcp/server.py:70` 注释）。

## 需求

1. **后端**：新增 `/api/project` 路由
   - `GET /api/project` → 读 `load_project()`，无数据时返回 `{"exists": false}`（200）
   - `PUT /api/project` → body 收完整 state dict，`project_from_dict` 还原校验后 `save_project()` 落盘，返回 `{"ok": true}`
   - 用 `lifespan`（或等价启动钩子）确保 data 目录/SQLite 就绪
2. **前端**：`useEditor` 增加「整体替换 doc」能力（reset/replace），供启动加载与后续恢复使用
3. **前端**：启动时 `GET /api/project`，有存档则替换 doc，无存档则保留 demo
4. **前端**：纯自动保存 —— `watch(doc)` 防抖（~500ms）后 `PUT /api/project` 全量 state；无手动保存按钮
5. 序列化契约与 `/api/export` 一致：`doc.value` 直接作为 state dict 传输；前端 `/media/*` 相对 src 原样存（落盘不转换，渲染/导出时才映射真实路径）

## 关键决策

- **保存触发 = 纯自动保存（无按钮）**：`watch(doc, ...)` → 防抖 `~500ms` → `PUT /api/project`。理由：目标「关浏览器不丢」强依赖自动落盘，手动按钮会让人忘记保存又丢数据；纯自动最简（KISS/YAGNI），不加状态指示 UI。
- **首次启动不主动回写 demo**：`watch(doc)` 默认不触发初始值，因此无存档时保留 demo 不落盘；用户第一次编辑时才 PUT 全量 doc（demo + 编辑）。demo 由代码静态定义，无需 seeding。
- **加载失败/无存档降级**：`GET` 出错或 `{exists:false}` 时静默回退 demo，不阻塞启动；保存失败静默（学习应用，不做错误 toast，可 console 留痕）。
- **单项目 last-write-wins**：无版本号/冲突检测，`project:default` 一 key 覆盖写。

## 验收标准

1. 后端 `GET /api/project` 首次返回 `{"exists": false}`；`PUT /api/project` 落盘后再次 `GET` 返回相同 doc（round-trip 一致）。
2. 前端刷新页面后，`doc` 与刷新前一致（持久化生效，不再回退到 demo 初始态）。
3. `save_project`/`load_project` 有 HTTP 调用方，`persist.py` 不再是「半死」；`grep -rn "save_project\|load_project" app` 能看到路由引用。
4. 后端 pytest 全绿（新增路由测试）；前端 tsc + vitest 全绿。
5. 现有 `/api/export`、`/api/agent-runs`、外部 MCP 链路不受影响。

## 非目标

- 多项目管理 / 项目列表 / 新建/切换项目（单 `project:default`）。
- 版本号/冲突检测（单用户 last-write-wins；claim/settle 的 baseRevision 机制不引入本任务）。
- 媒体文件上传/落盘（`/media/*` 仍是前端 public 静态资源，只持久化 src 字符串）。
- undo 历史持久化（只存 `present` 快照，不存 past/future 栈）。
- 保存失败重试/离线队列（后续）。
