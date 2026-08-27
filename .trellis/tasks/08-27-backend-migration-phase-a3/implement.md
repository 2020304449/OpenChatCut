# 实施计划 — 后端迁移 A-3

## 顺序

1. **A 类数据模型**：`domain/multicam.py` + `timeline.py`/`item.py` 加字段。
2. **A 类命令**：`TrackTighten`/`SetCanvas`/multicam/linkGroups 命令 + 单测。
3. **A 类工具**：`edit_track` 加 tighten、`set_aspect_ratio`、`change_cam`、`manage_link_group` + 单测。
4. **B1 LLM 重试**：`llm.py` 加重试 + 单测（mock 一个瞬时失败 LLM）。
5. **B2 token 流式**：`llm.py` 加 `stream_chat`、`loop.py` 消费流 + 单测。
6. **B3 自治验收**：loop 加 mutate 检测 + 验证注入 + 单测。
7. **B4 上下文压缩**：loop 加 token 估算 + 截断 + 单测。
8. **B5 持久化**：`persist.py` + main.py lifespan + 单测（save/load 往返）。
9. **验证**：全量 pytest + 前端手测（流式文本）。

## 验证命令

```bash
cd learning/openchatcut-backend/backend
.venv/Scripts/python.exe -m pytest -q
```

## 关键回滚点

- `loop.py`：B2/B3/B4 都改它，逐步改、每步跑测试。
- `llm.py`：B1/B2 改接口，保证 mock/真实一致。
- `persist.py`：`project_from_dict` 反序列化最易错，测往返。

## 完成前检查

- [ ] A 类 4 命令 + 工具全测过
- [ ] B1~B5 各有一项单测
- [ ] 全量 pytest 无回归
