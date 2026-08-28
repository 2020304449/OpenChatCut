"""agent-runs executor：async 版 LLM 循环（对齐 server/agent-runs/executor.ts）。

从 loop.py 迁移，关键改造：不再持有 Executor，工具执行改为产出 tool-request 事件 +
wait_for_tool_result 挂起，等 browser claim/settle 结算。
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator

from ..agent.loop import _compact, build_system_prompt
from ..agent.registry import ToolRegistry, build_registry
from .policy import requires_approval
from .store import ServerRun, await_approval, await_tool_result, register_tool_request

MAX_ITER = 20
VERIFY_ROUND_LIMIT = 3   # 验收轮次上限（验收 → 修正 → 再验收的累计次数）


async def execute_run(
    run: ServerRun,
    user_message: str,
    llm,
    initial_state: dict,
) -> AsyncIterator[dict]:
    tools = build_registry()
    if run.supported_tools:   # 能力协商：裁剪到 browser 声明的工具集
        supported = set(run.supported_tools)
        tools = ToolRegistry([t for t in tools.list() if t.name in supported])
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt(initial_state, tools)},
        {"role": "user", "content": user_message},
    ]

    run.state = "running"
    run.metrics.started_at_ms = int(time.time() * 1000)
    yield {"event": "state", "data": initial_state}

    mutated = False
    verifying = False        # 是否已进入验收阶段（已追加验收指令）
    verify_rounds = 0        # 累计验收次数（验收→修正→再验收）

    for _ in range(MAX_ITER):
        run.metrics.iterations += 1
        messages = _compact(messages)

        tool_calls = []
        try:
            for ev in llm.stream_chat(messages, tools.schemas()):
                if ev["type"] == "text":
                    yield {"event": "assistant", "data": {"text": ev["delta"]}}
                elif ev["type"] == "tool_calls":
                    tool_calls = ev["calls"]
        except Exception as exc:
            run.metrics.errors += 1
            yield {"event": "error", "data": {"message": f"LLM 调用失败：{exc}"}}
            break

        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                run.metrics.tool_calls += 1
                req = register_tool_request(run, tc.id, tc.name, tc.arguments,
                                            requires_approval=requires_approval(tc.name))

                # 高风险工具：先走审批，approved 后才 claim/settle，rejected 则跳过
                if req.status == "pending_approval":
                    run.metrics.approvals += 1
                    yield {"event": "approval_request", "data": {
                        "toolCallId": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }}
                    approved = await await_approval(req)
                    if not approved:
                        result = {"ok": False, "rejected": True}
                        yield {"event": "tool_result", "data": result}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                        continue

                yield {"event": "tool_request", "data": {
                    "toolCallId": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "argsDigest": req.args_digest,
                }}
                result = await await_tool_result(req)
                yield {"event": "tool_result", "data": result}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            mutated = True
            verifying = False   # 有工具调用 → 退出验收态，修正后可再次进入验收
        else:
            if not mutated:
                break  # 本就无工具调用
            if not verifying:
                # 首次无工具调用且已 mutate：进入验收，追加验收指令
                verify_rounds += 1
                if verify_rounds > VERIFY_ROUND_LIMIT:
                    yield {"event": "error", "data": {"message": f"验收轮次超限（{VERIFY_ROUND_LIMIT}），中止"}}
                    break
                verifying = True
                messages.append({
                    "role": "user",
                    "content": "请调用 read_timeline 核对结果是否符合意图；符合则简短总结，不符合请继续修正。",
                })
                continue
            break  # 已在验收且无工具调用 → 验收通过
    else:
        yield {"event": "error", "data": {"message": f"达到最大迭代次数 {MAX_ITER}，中止"}}

    run.state = "done"
    run.metrics.finished_at_ms = int(time.time() * 1000)
    if run.metrics.started_at_ms is not None:
        run.metrics.duration_ms = run.metrics.finished_at_ms - run.metrics.started_at_ms
    yield {"event": "done", "data": {}}
