# 技术设计 — AI 剪辑智能体最小克隆

## 架构总览

```
Vue3 前端 (ChatPanel / TimelineView / ToolCallLog)
      │  POST /api/chat (SSE 流)  ·  GET /api/state  ·  POST /api/undo|redo  ·  GET /api/tools
      ▼
FastAPI 后端
  ├── agent/loop.py      LLM 工具调用循环（流式，产出 SSE 事件）
  ├── agent/tools.py     工具 schema + execute（翻译层）
  ├── agent/registry.py  工具注册表 → 供 LLM 与 /api/tools 使用
  ├── editor/            不可变状态 + 命令 + 撤销栈（编辑核心）
  └── llm.py             OpenAI 兼容客户端（含 mock 模式）
```

### 与 OpenChatCut 的映射（学习对照表）

| 本克隆模块 | OpenChatCut 对应 | 说明 |
|---|---|---|
| `backend/editor/` | `src/editor/` | 编辑核心：命令层、不可变时间线状态 |
| `backend/agent/tools.py` | `src/agent/tools/`（172 文件） | 工具 schema + execute → 发命令 |
| `backend/agent/loop.py` | `server/agent-runs/executor.ts` + `src/agent/api-runtime.ts` | 模型循环 |
| `backend/llm.py` | `server/agent-runs/model.ts` | 多厂商 LLM（本克隆只做 OpenAI 兼容） |
| `(超纲) MCP` | `server/external-agent/mcp.ts` | 外部 Agent 入口，本克隆不做 |

## 目录结构

```
learning/vue3-python-clone/
├── README.md                    # 学习导引：怎么跑、对照 OpenChatCut 哪一段
├── docs/
│   └── ai-editing-agent-jingdu.md   # 交付物 1：架构精读（带锚点）
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py              # FastAPI app + 端点
│   │   ├── llm.py               # OpenAI 兼容 + mock
│   │   ├── editor/
│   │   │   ├── __init__.py
│   │   │   ├── model.py         # Timeline/Track/Clip（frozen dataclass）
│   │   │   ├── commands.py      # Command + Executor + 撤销栈
│   │   │   └── store.py         # 内存 ProjectStore（单工程）
│   │   └── agent/
│   │       ├── __init__.py
│   │       ├── tools.py         # 工具定义
│   │       ├── registry.py      # 注册表
│   │       └── loop.py          # 循环 + SSE
│   └── tests/
│       └── test_editor.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── main.ts
        ├── App.vue
        ├── api.ts               # SSE client + REST
        └── components/
            ├── ChatPanel.vue
            ├── TimelineView.vue
            └── ToolCallLog.vue
```

## 数据流（一次对话请求）

1. 前端 `POST /api/chat {"message": "加两个片段和一个字幕"}`，用 fetch + ReadableStream 读 SSE。
2. 后端 `loop.py` 读取当前时间线，拼成 system prompt（含时间线摘要 + 工具使用说明）。
3. 调 `llm.py` 的模型（mock 或真实），请求带工具 schema。
4. 模型返回 tool_call → `loop.py` 用 `registry` 找到工具 → `execute(args, ctx)` → 内部发 Command → `store.apply(command)`。
5. 每次状态变化，后端向前端推送 `state` 事件（完整时间线 JSON）。
6. 模型再收到 tool_result 继续，直到返回最终文本 → 推送 `done`。
7. 前端按事件流刷新：消息文本、工具日志、时间线视图。

## 契约

### REST 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | SSE 流，body `{"message": "..."}` |
| GET | `/api/state` | 返回当前时间线 JSON |
| POST | `/api/undo` | 撤销最近命令，返回新状态 |
| POST | `/api/redo` | 重做 |
| GET | `/api/tools` | 返回工具 schema 清单（学习用） |

### SSE 事件格式（`data:` 为单行 JSON）

```
event: assistant    data: {"delta": "好的，我来"}
event: tool_call    data: {"name": "add_clip", "args": {"label": "片段A", ...}}
event: state        data: {"tracks": [{"id": "v1", "clips": [...]}]}
event: error        data: {"message": "..."}
event: done         data: {}
```

## 编辑核心设计

### 数据模型（`model.py`，frozen dataclass）

```python
@dataclass(frozen=True)
class Clip:
    id: str
    label: str
    kind: str            # "video" | "caption" | ...
    start: float         # 秒
    duration: float

@dataclass(frozen=True)
class Track:
    id: str
    kind: str            # "video" | "caption"
    clips: tuple[Clip, ...]

@dataclass(frozen=True)
class Timeline:
    tracks: tuple[Track, ...]
```

### 命令协议（`commands.py`）

```python
class Command(ABC):
    def apply(self, state: Timeline) -> Timeline: ...
```

- Executor 维护 `undo_stack: list[Timeline]`（快照）与 `redo_stack`。
- `execute(cmd)`：把当前 state 压入 undo_stack → `state = cmd.apply(state)` → 清空 redo_stack。
- `undo()`：把当前 state 压入 redo_stack → 弹出 undo_stack 恢复。
- `redo()`：对称。

### 取舍：快照撤销 vs 逆命令

- OpenChatCut 用细粒度逆命令（`src/editor/` 下每条命令带逆操作），状态不可变、内存高效、可精确 diff。
- 本克隆用**快照撤销**：每条命令直接保存上一个完整状态。实现最简单、绝对正确，适合教学；代价是内存随历史线性增长。
- 这是刻意简化，在精读文档里明确标注「这里简化了，源码里是这样做的」。

## 工具设计（`tools.py` + `registry.py`）

每个工具由两部分组成：

```python
@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON Schema（Pydantic model_json_schema）
    execute: Callable[[dict, ToolContext], dict]
```

`ToolContext` 持有 `store` 与「发命令」的入口。`execute` 只做两件事：校验参数 → 发一条 Command → 返回可读结果（回填给 LLM）。

### MVP 工具清单（5 个）

| 工具 | 作用 | 发起的命令 |
|---|---|---|
| `list_timeline` | 读当前时间线（只读） | — |
| `add_clip(label, track, start, duration, kind)` | 加一个片段 | AddClip |
| `add_caption(text, start, duration)` | 加一条字幕 | AddCaption（内部即 AddClip kind=caption） |
| `set_clip_duration(clip_id, duration)` | 改时长 | SetClipDuration |
| `remove_clip(clip_id)` | 删除片段 | RemoveClip |

schema 通过 `GET /api/tools` 暴露，前端「工具调用日志」面板直接展示，方便学习「LLM 看到了什么 schema」。

## Agent 循环设计（`loop.py`）

```
messages = [system, user]
while True:
    resp = llm.chat(messages, tools=registry.schemas())
    if resp.tool_call:
        emit("tool_call", name, args)
        result = registry.execute(resp.tool_call)
        emit("state", store.state)
        messages.append(assistant_msg_with_tool_call, tool_result)
    else:
        emit("assistant", resp.text_delta)   # 流式文本
        if resp.finish: break
emit("done")
```

### mock LLM（`llm.py`）

`LLM_MOCK=1` 时，`llm.chat()` 不联网，而是返回一段**固定脚本**：例如检测到用户消息含「字幕」就依次返回 `add_clip`、`add_clip`、`add_caption` 三个 tool_call，再返回最终文本。用途：
- 无 API Key 时也能验证整条循环（编辑核心 + 工具 + SSE + 前端联动）。
- 前端/后端联调不消耗 token。
- 精读文档用它演示「LLM 的决定」是什么样子。

真实模式：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 走 `openai` 官方 SDK 的 `base_url` 覆盖，兼容 OpenAI / DeepSeek / Moonshot / 本地 Ollama 等。

## 前端设计（Vue3，无额外状态库）

- 状态用 Vue 3 `ref`/`reactive` 即可，MVP 不引入 Pinia。
- `api.ts`：`fetch` + `ReadableStream` 解析 SSE；`getState` / `undo` / `redo` 走 REST。
- `App.vue` 组织三块：`ChatPanel`（输入 + 消息流）、`ToolCallLog`（工具调用序列）、`TimelineView`（轨道/片段渲染）。
- 时间线是数据驱动渲染：直接根据 `/api/state` 的 `tracks` 画块，不涉及真实视频。

## 依赖与兼容性

- 后端：`fastapi`、`uvicorn[standard]`、`pydantic>=2`、`openai`、`httpx`。SSE 用 FastAPI 原生 `StreamingResponse`，不引入 sse-starlette（减少依赖面）。
- 前端：`vue`、`vite`、`@vitejs/plugin-vue`、`typescript`。
- Python：3.11+（dataclass / typing 现代语法）。
- 端口：后端 8000，前端 Vite 5173，`vite.config.ts` 配 `/api` 代理到 8000，避免 CORS。

## 风险与回滚

| 风险 | 应对 |
|---|---|
| 用户没有真实 LLM Key，跑不通 | mock 模式兜底；README 写清如何接 DeepSeek/本地 Ollama |
| SSE 跨端踩坑 | 前端代理 `/api` 到 8000，后端开 CORS 双保险 |
| 快照撤销内存增长 | MVP 单会话够用；README 注明这是教学简化 |
| 范围蔓延（想加渲染/真实视频） | 严格遵守 Out of Scope，后续可作为独立任务 |

## 验证

- `backend`: `pytest` 跑编辑核心单测；`uvicorn` 起服务后 curl 打 4 个端点。
- `frontend`: `npm run build` 通过 + `npm run dev` 浏览器手测。
- 端到端：mock 模式下一句指令 → 观察 SSE 工具调用 → 时间线 3 条目 → 撤销回退。
