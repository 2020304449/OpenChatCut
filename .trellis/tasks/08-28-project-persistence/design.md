# design：项目持久化端点

## 1. 后端 `/api/project`

### 1.1 路由（新文件 `app/project_routes.py`）

```python
router = APIRouter(prefix="/api/project")

@router.get("")
def get_project():
    doc = load_project()                    # 走默认路径（OPENCHATCUT_DATA_DIR 或 data/）
    if doc is None:
        return {"exists": False}
    return {"exists": True, "state": project_to_dict(doc)}

@router.put("")
def put_project(body: PutBody):             # PutBody.state: dict
    try:
        doc = project_from_dict(body.state)
    except Exception as exc:
        raise HTTPException(400, f"invalid project state: {exc}")
    save_project(doc)                        # 走默认路径
    return {"ok": True}
```

- `load_project`/`save_project` 不带 path 参数，走 `default_path()` → `data_dir()`，**尊重 `OPENCHATCUT_DATA_DIR` 环境变量**（测试用 `monkeypatch.setenv` 隔离，避免污染真实 `data/`）。
- `project_from_dict` 是「规范化 + 形状收敛」而非严格校验：`persist.py` 的 `_coerce` 对容器/嵌套 dataclass 递归反序列化，但基元类型不强制转换、未知字段静默丢弃（`app/persist.py:21-56`）。这符合「后端 dataclass 是 schema 权威」的既有约定，无需在本任务引入严格校验。

### 1.2 lifespan（`app/main.py`）

- 最小化：`@asynccontextmanager` lifespan 里 `os.makedirs(data_dir(), exist_ok=True)`，`yield` 后无清理。
- **不持有 SQLite 连接**：`persist.py` 的 `save_project`/`load_project` 每次 open→操作→close（`app/persist.py:100-104, 121-125`），学习应用低并发足够。持有单例连接需要额外生命周期管理，违反 KISS/YAGNI。
- `SqliteStore` 内部 `CREATE TABLE IF NOT EXISTS` + `os.makedirs`（`app/storage/sqlite_store.py:16-25`；`app/persist.py:98-99`）已兜底，lifespan 只是把 data 目录在启动时显式就绪。

## 2. 前端：启动加载 + 自动保存

### 2.1 `useEditor` 增加 `reset`（`src/editor/store.ts`）

```ts
export interface EditorStore {
  ...
  reset: (doc: ProjectDoc) => void
}

export function useEditor(initial: ProjectDoc): EditorStore {
  const h = ref<History>(initHistory(initial))
  ...
  function reset(doc: ProjectDoc): void {
    h.value = initHistory(doc)   // 替换 present + 清空 past/future
  }
  return { ..., reset }
}
```

- 复用 `initHistory`（`reduce.ts`），不新增 action 类型；`reset` 语义 = 「加载外部快照，丢弃 undo 历史」，与「只持久化 present」一致。
- 数据流：`reset(savedDoc)` → `h.value` 变化 → `doc`（`computed(() => h.value.present)`）自动响应。

### 2.2 bridge 客户端（新文件 `src/bridge/project.ts`）

```ts
export async function loadProject(): Promise<ProjectDoc | null> {
  const res = await fetch('/api/project')
  if (!res.ok) return null
  const body = await res.json()
  return body.exists ? (body.state as ProjectDoc) : null
}
export async function saveProject(doc: ProjectDoc): Promise<void> {
  await fetch('/api/project', { method: 'PUT', headers: {...}, body: JSON.stringify({ state: doc }) })
}
```

### 2.3 App.vue：hydration + 防抖自动保存

```ts
const { doc, commands, canUndo, canRedo, reset } = useEditor(demoProject())
const hydrated = ref(false)

onMounted(async () => {
  try { const saved = await loadProject(); if (saved) reset(saved) }
  catch (e) { console.warn('load project failed', e) }
  finally { hydrated.value = true }
})

let saveTimer: ReturnType<typeof setTimeout> | undefined
watch(doc, () => {
  if (!hydrated.value) return            // 加载阶段 reset 触发的 doc 变化不落盘
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveProject(doc.value).catch(e => console.warn('save failed', e)), 500)
})
```

**关键点：**
- `watch(doc)` 是浅监听——`historyReduce` 每次返回新 `present` 引用，命令 dispatch 后引用变化即触发，无需 `{ deep: true }`。
- **hydration 门控**：`onMounted` 里 `reset(saved)` 会改 `doc` 触发 watch，但 `hydrated` 仍 false → 跳过，避免「加载即回写一次」。设 true 后，后续编辑才触发保存。
- 首次无存档：不 reset、不保存，demo 保留在内存；用户第一次编辑才 PUT 全量 doc。
- 防抖 500ms，连续编辑合并为一次 PUT；保存失败静默 `console.warn`（决策：不做错误 toast）。

## 3. 序列化契约

- 传输 payload 与 `/api/export` 一致：`doc.value`（`ProjectDoc`）直接作为 `{ state }` 的 dict。
- `/media/*` 相对 src **原样落盘**，不映射真实路径（映射只在导出/渲染时发生，见 `app/export_routes.py:33-39`）。
- GET 返回 `project_to_dict(load_project())`（规范化形式），是 PUT 的稳定不动点；前端 `doc.value` 本就是 dataclass 形状，round-trip 无漂移。

## 4. 关键文件改动清单

- 后端新增：`app/project_routes.py`（路由）
- 后端改：`app/main.py`（挂 router + lifespan + `import os`）
- 后端新增测试：`tests/test_project_routes.py`（TestClient + `monkeypatch.setenv("OPENCHATCUT_DATA_DIR", tmp_path)`)
- 前端改：`src/editor/store.ts`（加 `reset`）、`src/App.vue`（hydration + 防抖自动保存）
- 前端新增：`src/bridge/project.ts`（load/save 客户端）、`src/editor/store.test.ts`（reset 语义）
