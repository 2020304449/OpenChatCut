# AI 剪辑智能体 · 最小克隆

学习并复刻 OpenChatCut 核心「AI 剪辑智能体」主线的最小项目：

```
自然语言 → LLM 工具调用 → 编辑核心命令 → 可撤销状态
```

- 后端：FastAPI（Python）
- 前端：Vue3 + Vite
- 目的：读懂 OpenChatCut 源码（见 `docs/ai-editing-agent-jingdu.md`）+ 亲手跑通最小闭环

## 目录结构

```
backend/
  app/
    editor/        # 编辑核心：model / commands（命令层）/ store（撤销栈）
    agent/         # tools（工具 schema + execute）/ registry / loop（模型循环）
    llm.py         # OpenAI 兼容客户端 + mock 模式
    main.py        # FastAPI 端点 + SSE
  tests/test_editor.py
frontend/
  src/
    api.ts         # SSE client + REST
    App.vue        # 组合根
    components/    # ChatPanel / TimelineView / ToolCallLog
docs/ai-editing-agent-jingdu.md   # 架构精读（带 OpenChatCut 锚点）
```

## 快速开始

### 1. 启动后端（默认 mock 模式，无需 API Key）

```bash
cd backend
python -m venv .venv
# Windows:
source .venv/Scripts/activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 ，在聊天框输入「加两个片段和一个字幕」，观察右侧
「工具调用」面板逐步出现 `add_clip` / `add_caption`，时间线同步长出片段，点「撤销」
回退。

### 3. 跑后端单测

```bash
cd backend
pytest -q
```

## 接真实 LLM（可选）

默认 `LLM_MOCK=1`，不联网。要接真实模型（OpenAI 兼容）时：

```bash
# Linux/macOS
export LLM_MOCK=0
export LLM_BASE_URL=https://api.openai.com/v1      # 或用 DeepSeek / Moonshot / 本地 Ollama
export LLM_API_KEY=sk-xxxx
export LLM_MODEL=gpt-4o-mini

# Windows PowerShell
$env:LLM_MOCK="0"; $env:LLM_BASE_URL="https://api.openai.com/v1"; ...

uvicorn app.main:app --port 8000
```

## 学习对照（读源码 + 读克隆）

核心机制与 OpenChatCut 的一一对应关系见 `docs/ai-editing-agent-jingdu.md`。
建议阅读顺序：

1. `backend/app/editor/commands.py` —— 对照 `src/editor/reducerActions.ts`（命令层）
2. `backend/app/agent/tools.py` —— 对照 `src/agent/tool-schema.ts` + `src/agent/tools/`（工具翻译层）
3. `backend/app/agent/loop.py` —— 对照 `server/agent-runs/executor.ts`（模型循环）
4. `backend/app/llm.py` —— 对照 `server/agent-runs/model.ts`（多厂商 LLM）

## 可选扩展（作为后续独立任务）

- 加 MCP 端点，让外部 Agent 也能调用工具
- 快照撤销 → 逆命令撤销
- token 级流式（真实 OpenAI streaming）
- 磁盘持久化（SQLite）
