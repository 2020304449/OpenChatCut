# 架构对齐 implement（骨架先行）

## 阶段 arch-1a：前端 TS EditorCore 骨架（最大，先做）

立住「browser 单一真源」：types + reduce + 快照栈 + draft + 13 骨架命令。

1. `frontend/src/editor/types.ts`：从 `api.ts` 类型升级为权威类型，补 Python domain 里前端还没对齐的字段（transform/keyframes/effects/reframeKeyframes/linkGroups/multicamGroups/transcript 等）。
2. `frontend/src/editor/reduce.ts`：`projectReduce(doc, action)` 纯函数 + `historyReduce` 快照栈（`HISTORY_LIMIT=100`，mutation 进历史、非 mutation 不进）。
3. `frontend/src/editor/commands.ts`：`buildCommands`，13 骨架命令 → action → dispatch。
4. `frontend/src/editor/draft.ts`：`makeDraft` + `replayActions`。
5. 测试：快照栈 undo/redo、13 骨架命令（对照 Python 命令的语义）。

**验证**：`npm run build` + `npx tsc --noEmit` 通过；新写的 editor 单测绿（若有 vitest，否则用轻量断言脚本）。

**回滚点**：纯新增 `editor/` 目录，不碰现有 `api.ts`/组件，可整体删除回退。

## 阶段 arch-1b：前端 TS 低频命令（机械翻译，可并行）

6. 剩余 ~65 命令按 Python `commands/` 模块分批翻译（transcript → item-attr → project → multicam）。

**验证**：每批对照 Python 语义补断言；全量 build + 类型检查绿。

## 阶段 arch-2：Python MCP server + broker + registry

7. `backend/app/mcp/server.py`：官方 `mcp` SDK 的 streamable_http transport，端点 `/api/external-mcp/mcp`，`mcp-session-id` + bearer token。
8. `backend/app/mcp/broker.py`：asyncio 长轮询（queues/pending/waiters，状态机 queued→in_flight→applied/stale/cancelled/rejected/failed，deadline 180s）。
9. `backend/app/mcp/registry.py`：`registerEditor`（baseRevision + tools）→ `registrationCapability` 鉴权。

**验证**：`/api/tools` 之外新增 MCP 端点可访问；broker 状态机单测（入队→取→结算→唤醒）。

## 阶段 arch-3：内部 run 的 claim/settle + LLM 循环迁移

10. `backend/app/agent_runs/routes.py`：`/api/agent-runs` 的 create/start/events/claim/result。
11. `backend/app/agent_runs/executor.py`：从 `loop.py` 迁移 LLM 循环，产出 tool-request + `waitForToolResult` 挂起。
12. `backend/app/agent_runs/store_tools.py`：`ServerToolRequest` + claimId/argsDigest/outcomeDigest 三重防护。

**验证**：mock LLM 走通「create → start → tool-request → claim → result → done」全链路。

## 阶段 arch-4：端到端接线

13. 前端 `bridge/serverRun.ts`（claim/settle 客户端）+ `bridge/externalBridge.ts`（broker 轮询客户端）。
14. `agent/tools.ts`（executeTool：工具 1:1 映射前端命令）+ 5 个 MCP 控制工具。
15. edit-session 三段式（begin → draft 执行 → review/apply）。

**验证**：外部 MCP 客户端（Claude/Codex）连入 → call_tool → broker → browser draft 执行 → apply 落库 → 结果回传。

## Review gate

- server 不直接改 ProjectDoc（代码审查可证）；edit-session draft 不污染真库直到 apply。
- 快照栈 undo/redo 正确；revision 防漂移生效。
- 两条链路（内部 claim/settle、外部 broker）等价跑通。

## 回滚

- 每阶段独立 commit；arch-1a 纯新增前端目录，整体可回退。
- 现有 `Executor`/`commands` 不删（降级 offline），能力补齐（cd）不回退。
