# 实施计划 — 后端迁移 A-2

## 实施顺序（每步完成后进入下一步）

1. **数据模型**：新增 `app/domain/transcript.py`（TranscriptWord/Variant/VariantWord + `ms_to_frame`）；`item.py` 加 transcript 字段。
2. **文本稿命令**（12 种）：`app/commands/transcript_actions.py`（新文件，避免 actions.py 过大）+ 单测。
3. **片段属性命令**（8 种）：加入 `actions.py` 或新文件 + 单测。
4. **项目级命令**（15 种）：加入 `actions.py` 或新文件 + 单测。
5. **工具面**（15~20 个）：`app/agent/tools.py` 扩展 + 单测。
6. **[DEFERRED] 标记**：tools.py 加 `DEFERRED_TOOLS` 注释块。
7. **验证**：pytest 全绿 + mock 闭环（删口误/停顿）+ 真实 LLM 可选。

## 验证命令

```bash
cd learning/openchatcut-backend/backend
.venv/Scripts/python.exe -m pytest -q      # 全绿
# mock 闭环：删口误和停顿
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
from app.agent.loop import run_agent
from app.commands.base import Executor
from app.domain.timeline import default_project
from app.llm import MockLlm
ex = Executor(default_project())
list(run_agent('删掉口误和停顿', ex, MockLlm()))
print('OK')
"
```

## 关键文件 / 回滚点

- `app/domain/transcript.py`：新数据模型 + `ms_to_frame`，先写 + 测。
- `app/commands/transcript_actions.py`：cleanScript/reorderTrackItems 算法最易错，重点测。
- `app/domain/item.py`：TimelineItem 加字段，注意保持 A-1 既有字段不破坏。
- 回滚：A-2 是增量，只加文件/加字段，不删 A-1 既有代码；出问题回退单个 commit 即可。

## 完成前检查

- [ ] 35 种命令每种有 apply + 断言
- [ ] `ms_to_frame` 正确（30fps 下 1000ms=30 帧）
- [ ] cleanScript 边界（空 transcript/单词/相邻填充词）测试通过
- [ ] 工具面覆盖全部新增命令
- [ ] `grep -rn "DEFERRED" app/` 能找到全部延后标记
- [ ] A-1 的 32 个测试不回归
