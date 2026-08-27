# 后端迁移 A-3: 补边角命令 + Agent 循环工程化

## Goal

补全 A-1/A-2 遗留的 A 类编辑命令边角，并给 Agent 循环加上 B 类工程化健壮性，让后端从「能跑」向「生产可用」靠拢。

## Requirements

### A 类 — 编辑命令边角（4 项）

- **A1 track.tighten**：`TrackTighten` 命令，把同轨道 item 按 startFrame 紧凑排列去空隙；`edit_track` 加 `tighten` action。
- **A2 setCanvas**：`SetCanvas` 命令（width/height/fit）；新增 `set_aspect_ratio` 工具。
- **A3 multicam**：数据模型加 `Timeline.multicamGroups`（`MulticamGroup`：angles/evidence/decisions）+ `TimelineItem.multicamGroupId/multicamAngleId`；`change_cam` 工具（区间切机，非破坏性决策）。
- **A4 linkGroups**：数据模型加 `Timeline.linkGroups`（`TimelineLinkGroup`：itemIds/anchorItemId/mode）；`manage_link_group` 工具。

### B 类 — Agent 循环工程化（5 项）

- **B1 LLM 重试**：`OpenAiLlm` 对瞬时失败（限流/超时/传输）退避重试（最多 3 次），确定性失败直接抛。
- **B2 token 级流式**：`llm.py` 提供 `stream_chat` 生成器（text_delta / tool_calls / done）；`loop.py` 消费流，把文本增量实时 yield 给前端；mock 也走同一流式接口。
- **B3 自治验收**：简化版——若最后一轮发生 mutate（工具调用），追加一条验证指令让模型用 read 工具确认，再收尾。
- **B4 上下文压缩**：简化版——估算消息 token（字符数启发式），超阈值时注入「压缩历史」摘要并截断旧消息。
- **B5 run 持久化**：`app/persist.py` 用 JSON 文件快照 ProjectDoc；FastAPI lifespan 启动加载、关闭保存；进程重启不丢状态。

## Acceptance Criteria

- [ ] A 类 4 命令各有 apply + 断言；`edit_track`/`set_aspect_ratio`/`change_cam`/`manage_link_group` 工具经 registry 可执行。
- [ ] multicam/linkGroups 数据模型 `to_dict` 往返无损。
- [ ] B1：mock 一个会瞬时失败的 LLM，验证重试后成功 / 确定性失败不重试。
- [ ] B2：流式接口产出 text_delta 事件，前端可逐步收到文本。
- [ ] B3：mutate 后追加验证指令；纯读不追加。
- [ ] B4：超长消息历史被压缩/截断，不崩。
- [ ] B5：save→重启→load 后 ProjectDoc 一致。
- [ ] 全量 pytest 不回归（现有 55 + 新增）。

## Out of Scope

- 生成/导出/multicam 高级同步算法（audio 相关同步证据）/重计算类智能（同 A-2 的 [DEFERRED]）
- MCP、前端、SQLite 持久化（B5 用 JSON 快照，不是数据库）
- token 精确计数（B4 用启发式估算，不接 tokenizer）

## Key Decisions

- B2 流式接口统一：mock 与真实 LLM 都实现 `stream_chat(messages, tools) -> Iterator[dict]`，loop 只消费这个接口。
- B3 验收是「追加验证指令」而非完整状态机（OpenChatCut 有 AcceptanceLoop 状态机，这里简化为一次 verify 提示）。
- B4 压缩用字符数/4 估算 token（中英文混合的粗糙启发式），不做精确 tokenizer。
- B5 用 JSON 文件（`data/project.json`）而非 SQLite，保持零新依赖。
