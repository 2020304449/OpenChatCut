"""Agent 循环共享函数：系统提示词构造 + 上下文压缩（对齐 server/agent-runs/executor.ts）。

本迁移为 browser 权威架构：LLM 循环已迁到 agent_runs/executor.py（async，产 tool-request 事件），
本模块只保留 executor 复用的纯函数：build_system_prompt / _compact / _estimate_tokens。
含 B 类工程化：上下文压缩（token 估算 + 截断）。
"""
from __future__ import annotations

import json

from .registry import ToolRegistry

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
