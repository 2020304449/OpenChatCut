# 实施计划 — 后端迁移 A-1

## 实施顺序（每步完成后进入下一步）

1. **骨架**：建 `learning/openchatcut-backend/backend/` 目录树，`requirements.txt`（fastapi/uvicorn/pydantic/openai/pytest）+ `pytest.ini`。
2. **数据模型**（`app/domain/`）：`media.py` → `track.py` → `item.py` → `transition.py` → `marker.py` → `captions.py` → `timeline.py`（含 `ProjectDoc` + `to_dict`）。
3. **命令层**（`app/commands/`）：`base.py`（Command + Executor 快照撤销）→ `actions.py`（38 种命令）。
4. **单测**：`test_domain.py`（往返序列化）+ `test_commands.py`（每命令 apply + undo/redo）。
5. **工具层**（`app/agent/`）：`tools.py`（~20 工具 schema + execute）→ `registry.py`。
6. **LLM**（`app/llm.py`）：OpenAI 兼容 + mock（复用最小克隆思路）。
7. **循环 + 端点**（`app/agent/loop.py` + `app/main.py`）：SSE 流 + REST 端点。
8. **端到端测试**：`test_tools.py`（工具 execute）+ `test_loop.py`（mock 闭环：加片段 + 转场 + 字幕）。

## 验证命令

```bash
cd learning/openchatcut-backend/backend
python -m venv .venv && source .venv/Scripts/activate   # Windows
pip install -r requirements.txt
pytest -q                                              # 全绿
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "   # mock 端到端
from app.editor...  # 见 tests
"
LLM_MOCK=1 uvicorn app.main:app --port 8000             # 起服务
curl -s localhost:8000/api/tools                        # 工具 schema
curl -s localhost:8000/api/state                        # 空项目
```

## 关键文件 / 回滚点

- `app/commands/base.py`：撤销栈核心，最先写 + 测。
- `app/domain/timeline.py`：`ProjectDoc` + `to_dict`，所有命令的输入输出，字段对齐 `clipTypes.ts` 等。
- `app/commands/actions.py`：38 种命令，按类别分组，最易遗漏字段。
- 回滚：全新目录 `learning/openchatcut-backend/`，不触碰现有代码，回滚即删目录。

## 完成前检查

- [ ] `pytest` 全绿（domain / commands / tools / loop 四类）
- [ ] 数据模型核心字段往返序列化无损
- [ ] 38 种命令每种至少一条 apply 断言 + undo/redo 正确
- [ ] mock 闭环：一句含「加片段 + 转场 + 字幕」指令 → 对应 tool_call → 时间线反映改动 → undo 回退
- [ ] `GET /api/tools` 返回核心工具 schema；`GET /api/state` 返回空项目
