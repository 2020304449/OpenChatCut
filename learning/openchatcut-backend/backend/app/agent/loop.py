"""Agent 循环：多轮工具调用直到完成，产出 SSE 事件流。

对照 OpenChatCut `server/agent-runs/executor.ts`。本迁移为单体后端（无浏览器分离）。
含 B 类工程化：token 流式（消费 llm.stream_chat）、自治验收（mutate 后 verify）、
上下文压缩（token 估算 + 截断）。
"""
from __future__ import annotations

import json
from typing import Iterator

from ..domain.timeline import project_to_dict
from .registry import ToolContext, ToolRegistry, build_registry

MAX_ITER = 20
MAX_CONTEXT_TOKENS = 12000     # B4 启发式阈值（字符数/4 估算，留余量）


def build_system_prompt(project: dict, tools: ToolRegistry) -> str:
    state_json = json.dumps(project, ensure_ascii=False, indent=2)
    tool_names = ", ".join(t.name for t in tools.list())
    return (
        "你是一个视频剪辑智能体。用户用自然语言描述剪辑意图，你通过调用工具修改时间线工程。\n"
        f"可用工具：{tool_names}\n"
        f"当前工程状态（JSON）：\n{state_json}\n\n"
        "规则：\n"
        "- 每个操作都必须通过工具完成，不要凭空声称已完成。\n"
        "- 加画面片段用 add_clip（轨道 V1），加字幕用 edit_captions，加转场用 add_transition。\n"
        "- 时间单位是帧（startFrame/durationInFrames），默认 fps=30。\n"
        "- 完成后用一句简短的中文总结你做了什么。"
    )


def _estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += len(str(m.get("content") or ""))
        if "tool_calls" in m:
            total += len(json.dumps(m.get("tool_calls"), ensure_ascii=False))
    return total // 4


def _compact(messages: list[dict]) -> list[dict]:
    """超阈值时保留 system + 最近 6 条，中间替换为摘要。"""
    if _estimate_tokens(messages) <= MAX_CONTEXT_TOKENS:
        return messages
    return [messages[0],
            {"role": "user", "content": "（前文对话已压缩，请基于当前时间线状态继续任务）"}] \
        + messages[-6:]


def run_agent(user_message: str, executor, llm) -> Iterator[dict]:
    """执行一轮对话，逐个产出 SSE 事件（{"event": ..., "data": ...}）。"""
    tools = build_registry()
    ctx = ToolContext(executor)
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt(project_to_dict(executor.state), tools)},
        {"role": "user", "content": user_message},
    ]

    yield {"event": "state", "data": project_to_dict(executor.state)}

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
        except Exception as exc:  # LLM 网络/API 错误：转为 error 事件而非中断 SSE 流
            yield {"event": "error", "data": {"message": f"LLM 调用失败：{exc}"}}
            break

        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                yield {"event": "tool_call", "data": {"name": tc.name, "arguments": tc.arguments}}
                result = tools.execute(tc.name, tc.arguments, ctx)
                yield {"event": "tool_result", "data": result}
                yield {"event": "state", "data": project_to_dict(executor.state)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            mutated = True
        else:
            # B3: 本轮发生 mutate 且尚未验证 → 追加验证指令再跑一轮
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

    yield {"event": "done", "data": {}}
