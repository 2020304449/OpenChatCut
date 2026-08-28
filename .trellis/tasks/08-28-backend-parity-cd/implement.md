# C+D 能力补齐 implement

## 阶段 1：SQLite KV 持久化（基础，先做）

1. 新建 `backend/app/storage/__init__.py` + `sqlite_store.py`：`kv(k,v)` + `storage_migration_state`，WAL，`BEGIN IMMEDIATE`，`get/put/delete`。
2. 改 `backend/app/persist.py`：`save_project`/`load_project` 改走 SQLite `project:<id>`；首启若 DB 无 receipt 且存在旧 `data/project.json`，导入并写 receipt；receipt 缺失时回退 JSON。
3. 测试：`tests/test_sqlite.py`（roundtrip、迁移、幂等、重启恢复）。

**验证**：`./.venv/Scripts/python.exe -m pytest -q` 全绿，且 `persist` 相关旧测试仍过。

**回滚点**：persist 改动是纯替换，可 `git checkout` 回退到 JSON 快照。

## 阶段 2：服务层骨架

4. 新建 `backend/app/services/`：`probe.py`（ffprobe）、`export.py`（FFmpeg filter_complex 生成 + 执行）、`subtitles.py`（SRT）、`fcpxml.py`（FCPXML 最小）、`transcription.py`（faster-whisper 懒加载）。
5. 依赖：`requirements.txt` 加 `faster-whisper`；ffmpeg/ffprobe 用 `OPENCHATCUT_FFMPEG`/`OPENCHATCUT_FFPROBE` 覆盖否则 PATH。
6. 服务函数对「依赖缺失」返回结构化错误，不崩溃。

**验证**：`python -c "import app.services.probe"` 等模块可导入；对不存在依赖的机器，`probe_media` 返回 `{ok:false, error}`。

## 阶段 3：18 个工具 mock 存根

7. 新建 `backend/app/agent/mock_generation.py`：`MockJobStore`（jobId→status/result）+ 各工具的 mock executor（同步假资产 / 异步假 job）。
8. 在 `backend/app/agent/tools.py` 注册 18 个工具（args_model 用 Pydantic 对齐原版关键参数 + 返回契约），从 `DEFERRED_TOOLS` 移除。
9. `transcribe_track` 与 `probe_media` 接真实服务（阶段 2 的 `services/`），其余生成类走 mock。

**验证**：`/api/tools` 返回 65 工具；`tests/test_tools.py` 断言 18 个新工具存在且可执行。

## 阶段 4：端到端 + 测试补全

10. `tests/test_generation_mock.py`：同步/异步 mock、track_progress、rerun_generation、幂等。
11. `tests/test_services.py`：probe/export/subtitles/transcription（依赖存在时跑真实，缺失时跳过）。
12. 全量 `pytest` + 手动跑一次 agent（mock LLM）触发生成类工具，确认循环不因 mock 断链。

**验证**：全量 pytest 绿；agent mock 端到端跑通「提交生成 → track_progress → 取结果」。

## Review gate

- 65 工具 schema 与返回契约对齐原版（对照 `deferred-tools.md`）。
- SQLite 迁移不丢数据、幂等。
- 服务层依赖缺失时优雅降级。

## 回滚

- 每阶段独立提交；阶段间可回退。
- SQLite 有 JSON 回退路径；服务层有依赖缺失降级。
