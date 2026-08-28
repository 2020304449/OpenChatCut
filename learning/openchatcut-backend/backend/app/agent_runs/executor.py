"""agent-runs executor：async 版 LLM 循环（对齐 server/agent-runs/executor.ts）。

从 loop.py 迁移，关键改造：不再持有 Executor，工具执行改为产出 tool-request 事件 +
wait_for_tool_result 挂起，等 browser claim/settle 结算。
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from ..agent.loop import _compact, build_system_prompt
from ..agent.registry import build_registry
from .store import ServerRun, await_tool_result, register_tool_request

MAX_ITER = 20


async def execute_run(
    run: ServerRun,
    user_message: str,
    llm,
    initial_state: dict,
) -> AsyncIterator[dict]:
    tools = build_registry()
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt(initial_state, tools)},
        {"role": "user", "content": user_message},
    ]

    run.state = "running"
    yield {"event": "state", "data": initial_state}

    mutated = False
    verified = False

    for _ in range(MAX_ITER):
        messages = _compact(messages)

        tool_calls = []
        try:
            for ev in llm.stream_chat(messages, tools.schemas()):
                if ev["type"] == "text":
                    yield {"event": "assistant", "data": {"text": ev["delta"]}}
                elif ev["type"] == "tool_calls":
                    tool_calls = ev["calls"]
        except Exception as exc:
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
                req = register_tool_request(run, tc.id, tc.name, tc.arguments)
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
        else:
            if mutated and not verified:
                messages.append({
                    "role": "user",
                    "content": "请用 read_timeline 或 read_project 验证最新时间线状态，确认改动已生效，然后简短总结。",
                })
                verified = True
                continue
            break
    else:
        yield {"event": "error", "data": {"message": f"达到最大迭代次数 {MAX_ITER}，中止"}}

    run.state = "done"
    yield {"event": "done", "data": {}}
