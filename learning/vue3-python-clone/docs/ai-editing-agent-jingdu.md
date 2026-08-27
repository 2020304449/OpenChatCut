# AI 剪辑智能体是怎么开发的 — 架构精读

> 对照对象：OpenChatCut 源码（本仓库根目录）与本仓库的最小克隆（`learning/vue3-python-clone/`）。
> 目标：用「读源码 + 亲手复刻最小闭环」两步，吃透 AI 剪辑智能体的开发机制。

## 一句话概括

OpenChatCut 的「AI 剪辑智能体」**不是一个「生成视频」的魔法盒子**，而是一个
**LLM 工具调用循环** 加一个 **与 UI/LLM 无关的编辑核心**。它做的不是一次性生成一段
不可改的视频，而是把自然语言翻译成一条条可校验、可撤销的时间线命令。

---

## 三层结构

### 第 1 层：EditorCore（编辑核心）— 地基，`src/editor/`

这是整个项目最关键的设计决策：**把领域模型（时间线）和 LLM 彻底解耦**。

- 时间线状态是**不可变**的；所有修改都通过「命令」（command/action）完成。
- UI 和 LLM 都只能通过同一套命令改工程，所以每一步都可校验、可撤销、可预览。

最有力的一条证据在 `src/editor/reducerActions.ts:30`：

```ts
// ── command actions (these map 1:1 to the future agent tools) ─────────────
```

这条注释点破了整个架构的核心：**编辑命令和 Agent 工具是一一对应的**。下面
`src/editor/reducerActions.ts:31-80` 是一大串 `Action` 联合类型——`add`、`updateProps`、
`move`、`remove`、`split`、`setVolume`……每一条都是一个可撤销的命令。Agent 不是直接
改 React state，而是发命令，命令落到不可变状态上产生新状态。

### 第 2 层：Agent 工具面（翻译层）— `src/agent/tools/`（172 个文件）

每个工具 = **一个 schema + 一个 execute**，这就是「自然语言 → 结构化操作」的翻译层。

schema 的定义在 `src/agent/tool-schema.ts:1-10`：

```ts
export interface AgentToolSchema {
  name: string;
  description?: string;
  input_schema: {
    type: 'object';
    properties?: Record<string, unknown>;
    required?: string[];
  };
}
```

这就是发给 LLM 的「函数说明书」——LLM 据此决定调用哪个工具、传什么参数。

execute 内部只做两件事：**校验参数 → 发一条 EditorCore 命令**。看
`src/agent/tools/core-tools.ts:71`：

```ts
ctx.commands.addMotionGraphic(template, { track, startFrame, ripple: args.ripple === true });
```

以及 `src/agent/tools/core-tools.ts:118` 的 `ctx.commands.addAsset(asset)`。注意这里没有
直接操作 DOM 或 React state，只有 `ctx.commands.xxx()`——命令进入 EditorCore。

### 第 3 层：模型循环（决策层）— `server/agent-runs/`

- `server/agent-runs/model.ts:1-64`：用 Vercel AI SDK（`@ai-sdk/*`）接十几个厂商
  （Anthropic / OpenAI / Gemini / DeepSeek / Kimi / Qwen …），统一走本地 `/llm` 代理——
  **密钥只进服务端，不进浏览器**。
- `server/agent-runs/executor.ts`：核心是 `streamText(...)`（第 2 行引入）。每轮把
  `messages + tools` 交给模型，模型要么返回文本、要么返回 tool_call；执行工具后把结果
  回填，继续循环。还带重试（`llm-retry`）、上下文压缩（context overflow 时压缩后重试，
  见 `executor.ts:111-130`）、接受循环（`acceptance-loop`）。

三层串起来就是：

```
LLM（模型循环）→ 工具调用（schema）→ EditorCore 命令 → 不可变状态 + 撤销栈
```

---

## 主线数据流

```
描述目标 → Agent 读取工程（工具）→ LLM 决定调哪个工具、传什么参数（模型循环）
        → 工具校验参数、发 EditorCore 命令（翻译层）
        → 命令作用于不可变状态、产生新状态 + 撤销节点（编辑核心）
        → 预览 / 调整 / 撤销 → 字幕与混音 → 导出
```

---

## 两个增强（非核心机制，但值得了解）

### Skills — `src/agent/skills/`（26 个 `SKILL.md`）

教 Agent 做多步骤复杂工作流，例如「长视频转短视频」（`long-video-to-shorts`）、
「口播精剪」（`talking-head-guide`）。本质是**过程性提示词**——把「先转写 → 找停顿 →
删冗余 → 加字幕」这类流程写成步骤，喂给核心循环当领域知识。它们不是核心机制，是
给循环提供的「手艺」。

### MCP — `server/external-agent/mcp.ts`

把同一套工具暴露成 Streamable HTTP MCP（`http://localhost:5199/api/external-mcp/mcp`），
让 Codex / Claude Code 等外部 Agent 也能调用内置工具。内置 Agent 和外部 Agent
**共享同一套工具面**，不存在两套会漂移的工程格式。外部修改先进入隔离草稿，经
`begin_edit_session` → `review_edit_session` 审批后，原子提交为一个撤销节点。

---

## 与最小克隆的对应关系

本仓库 `learning/vue3-python-clone/` 就是这条主线的 Python 复刻。逐模块对照：

| OpenChatCut | 最小克隆（Python） | 说明 |
|---|---|---|
| `src/editor/reducerActions.ts`（Action 联合类型） | `backend/app/editor/commands.py`（Command 类） | 命令层 |
| `src/editor/`（不可变时间线状态） | `backend/app/editor/model.py`（frozen dataclass） | 状态 |
| `src/agent/tool-schema.ts`（AgentToolSchema） | `backend/app/agent/tools.py`（Pydantic args_model） | 工具 schema |
| `src/agent/tools/core-tools.ts`（execute → ctx.commands） | `backend/app/agent/tools.py`（exec_* → store.apply） | 翻译层 |
| `server/agent-runs/executor.ts`（streamText 循环） | `backend/app/agent/loop.py`（run_agent） | 模型循环 |
| `server/agent-runs/model.ts`（多厂商） | `backend/app/llm.py`（OpenAI 兼容 + mock） | LLM |
| `server/external-agent/mcp.ts` | （超纲，未做） | MCP |

---

## 简化说明（克隆 vs 源码，刻意为之）

| 维度 | 最小克隆 | OpenChatCut |
|---|---|---|
| 撤销 | 快照撤销（每条命令保存上个完整状态） | 细粒度逆命令（省内存、可精确 diff） |
| 流式 | 每轮一次 completion | Vercel AI SDK `streamText` 逐 token 流式 |
| 持久化 | 内存态 | SQLite / IndexedDB / R2 |
| 工具数量 | 5 个 | 172 个 |
| 渲染 | 无（数据驱动画块） | Remotion + WebGL + FFmpeg |

理解这些差异，比「把代码抄下来」更有价值：它们说明哪些是**机制**（循环、命令、工具
翻译），哪些是**工程量**（渲染、持久化、多厂商适配）。
