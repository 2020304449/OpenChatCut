# AI 剪辑智能体最小克隆 + 精读

## Goal

学习并复刻 OpenChatCut 的核心「AI 剪辑智能体」主线——即「自然语言 → LLM 工具调用 → 编辑核心命令 → 可撤销状态」这条闭环——并用一个能真正跑起来的最小项目验证理解。

两个交付物：

1. **精读文档**：一份中文架构精读，讲透这条主线，带 OpenChatCut 源码的 file:line 锚点。
2. **最小克隆**：一个全新项目（Vue3 前端 + FastAPI/Python 后端），跑通最小闭环。

用户价值：通过「读源码 + 亲手复刻最小闭环」两步，真正吃透 AI 剪辑智能体的开发机制，而不是只看文档或只看代码。

## Requirements

### R1 — 精读文档
- 一份中文文档，聚焦「AI 剪辑智能体是如何开发的」。
- 拆解 OpenChatCut 的关键机制，带 `D:\code\OpenChatCut` 下的 file:line 锚点。
- 覆盖主线：模型循环 → 工具调用 → EditorCore 命令 → 撤销栈；以及 Skills、MCP 两个增强。

### R2 — 编辑核心（后端）
- 简单时间线数据模型：多轨（Track）、片段（Clip，含 id / start / duration / label / kind）。
- 命令层：每个操作是一条 Command，作用于不可变状态，产出新状态。
- 撤销 / 重做：可回退到上一个状态。

### R3 — Agent 工具面（后端）
- 3~5 个工具，每个 = 参数 schema（Pydantic）+ execute()，execute 内部发命令。
- 工具清单可查询（`GET /api/tools`），供前端展示与学习。

### R4 — Agent 循环（后端）
- 一个端点接收自然语言，调用 LLM（OpenAI 兼容，环境变量可配置），多轮执行工具调用直到完成。
- 结果通过 SSE 流式返回：文本增量 + 工具调用事件 + 每次命令后的时间线状态。
- 必须支持「mock LLM」模式：不依赖真实 API Key 也能跑通循环（用于学习与无网测试）。

### R5 — 前端（Vue3）
- 聊天输入 + 消息流（SSE 实时展示 Agent 的文本与工具调用过程）。
- 时间线简视图（渲染轨道与片段）。
- 撤销按钮（触发后端 undo，界面同步刷新）。

## Acceptance Criteria

- [ ] `backend` 编辑核心单元测试通过（覆盖 add / remove / undo / redo）。
- [ ] 后端 `GET /api/state` 返回空时间线；`POST /api/undo` 在无历史时安全返回。
- [ ] mock LLM 模式下，输入一句含「加两个片段 + 一个字幕」的指令，会产生对应的 tool_call 事件，且最终时间线包含 3 个条目（无需真实 API Key）。
- [ ] 配置真实 LLM Key 后，同样的指令也能跑通（OpenAI 兼容厂商）。
- [ ] 前端 `npm run dev` 可渲染聊天、时间线、工具调用日志，SSE 实时更新。
- [ ] 撤销按钮回退最近一次命令，时间线同步变化。
- [ ] 精读文档存在，且包含 OpenChatCut 的 file:line 锚点。

## Out of Scope

- Remotion 渲染、WebGL/GLSL 特效、真实视频文件处理
- 多厂商模型适配（只做 OpenAI 兼容）
- MCP server、Electron、多工程、磁盘持久化（内存即可）
- 认证 / 多租户

## Key Decisions

- 后端选 Python + FastAPI（AI 智能体生态兼容性最好，MCP / LangGraph / 媒体处理均 Python-first）。
- LLM 走 OpenAI 兼容客户端 + 环境变量配置 + mock 模式（降低学习门槛，无 Key 也能跑）。
- 编辑核心用「不可变状态 + 快照撤销」：OpenChatCut 用更细粒度的逆命令，MVP 用快照是刻意简化，已在 design.md 记录。
- 新项目放 `learning/vue3-python-clone/`。
