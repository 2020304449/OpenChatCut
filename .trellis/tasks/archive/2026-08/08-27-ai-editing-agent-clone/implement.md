# 实施计划 — AI 剪辑智能体最小克隆

## 实施顺序（每步完成后再进入下一步）

1. **骨架**：建 `learning/vue3-python-clone/` 目录树；后端 `requirements.txt`、前端 `package.json` + `vite.config.ts` + `index.html`；`README.md` 骨架。
2. **编辑核心**（`backend/app/editor/`）：`model.py` → `commands.py` → `store.py`；写 `tests/test_editor.py`（add / remove / set_duration / undo / redo）。
3. **工具面**（`backend/app/agent/`）：`tools.py`（5 个工具）+ `registry.py`；`ToolContext` 接 `store`。
4. **LLM 客户端**（`backend/app/llm.py`）：OpenAI 兼容 + mock 模式（固定脚本）。
5. **循环 + 端点**（`backend/app/agent/loop.py` + `main.py`）：SSE 流 + `state`/`undo`/`redo`/`tools` 端点。
6. **前端**（`frontend/src/`）：`api.ts` → `ChatPanel.vue` → `ToolCallLog.vue` → `TimelineView.vue` → `App.vue`。
7. **精读文档**（`docs/ai-editing-agent-jingdu.md`）：交付物 1，带 OpenChatCut file:line 锚点。
8. **端到端验收**：mock 模式跑通完整闭环。

## 验证命令

```bash
# 后端单测
cd learning/vue3-python-clone/backend
python -m venv .venv && source .venv/Scripts/activate   # Windows
pip install -r requirements.txt
pytest -q

# 后端起服务 + 端点冒烟
LLM_MOCK=1 uvicorn app.main:app --port 8000
curl -s localhost:8000/api/state
curl -s localhost:8000/api/tools

# 前端
cd ../frontend && npm install && npm run build && npm run dev
```

## 关键文件 / 回滚点

- `backend/app/editor/commands.py`：撤销栈逻辑是核心，最先测。
- `backend/app/agent/loop.py`：循环最容易出边界 bug（空 tool_call、max_iter 上限），加 `max_iter` 防死循环。
- `backend/app/llm.py`：mock 脚本决定「无 Key 可跑」，保持纯函数、易替换。
- 回滚：本任务为全新目录 `learning/vue3-python-clone/`，不触碰现有 `src/`、`server/` 代码，回滚即删目录。

## 完成前检查

- [ ] `pytest` 全绿
- [ ] mock 模式端到端：一句指令 → 工具调用 → 时间线 3 条目 → 撤销回退
- [ ] 前端 `npm run build` 通过，`npm run dev` 浏览器手测 SSE 实时更新
- [ ] 精读文档含 file:line 锚点且可对照 OpenChatCut 源码
