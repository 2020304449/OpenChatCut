"""Agent 循环：多轮工具调用直到完成，产出 SSE 事件流。

对照 OpenChatCut `server/agent-runs/executor.ts`（streamText + 工具执行 + 重试 +
接受循环）。本克隆是简化版：每轮一次 completion，非 token 级流式（真实版用
Vercel AI SDK 的 streamText 逐 token 流式，这里简化为每轮整段，便于看清循环骨架）。
"""
from __future__ import annotations

import json
from typing import Iterator

from ..editor.model import timeline_to_dict
from ..llm import ChatResponse
from .registry import ToolContext, ToolRegistry, build_registry

MAX_ITER = 10


def build_system_prompt(timeline: dict, tools: ToolRegistry) -> str:
    state_json = json.dumps(timeline, ensure_ascii=False, indent=2)
    tool_names = ", ".join(t.name for t in tools.list())
    return (
        "你是一个视频剪辑智能体。用户会用自然语言描述剪辑意图，你通过调用工具修改时间线。\n"
        f"可用工具：{tool_names}\n"
        f"当前时间线状态（JSON）：\n{state_json}\n\n"
        "规则：\n"
        "- 每个操作都必须通过工具完成，不要凭空声称已完成。\n"
        "- 加字幕用 add_caption（落到 c1 轨），加画面用 add_clip（落到 v1 轨）。\n"
        "- 完成后用一句简短的中文总结你做了什么。"
    )


def run_agent(user_message: str, store, llm) -> Iterator[dict]:
    """执行一轮对话，逐个产出 SSE 事件（{"event": ..., "data": ...}）。"""
    tools = build_registry()
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt(timeline_to_dict(store.state), tools)},
        {"role": "user", "content": user_message},
    ]

    yield {"event": "state", "data": timeline_to_dict(store.state)}

    for _ in range(MAX_ITER):
        resp: ChatResponse = llm.chat(messages, tools.schemas())

        if resp.tool_calls:
            # 把模型的 tool_calls 记入消息历史（真实 OpenAI 需要这个格式）
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                    }
                    for tc in resp.tool_calls
                ],
            })
            for tc in resp.tool_calls:
                yield {"event": "tool_call", "data": {"name": tc.name, "arguments": tc.arguments}}
                result = tools.execute(tc.name, tc.arguments, ToolContext(store))
                yield {"event": "tool_result", "data": result}
                yield {"event": "state", "data": timeline_to_dict(store.state)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        else:
            yield {"event": "assistant", "data": {"text": resp.text}}
            break
    else:
        yield {"event": "error", "data": {"message": f"达到最大迭代次数 {MAX_ITER}，中止"}}

    yield {"event": "done", "data": {}}
