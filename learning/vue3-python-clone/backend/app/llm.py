"""LLM 客户端：OpenAI 兼容 + mock 模式。

真实模式走 openai 官方 SDK 的 base_url 覆盖，兼容 OpenAI / DeepSeek / Moonshot /
本地 Ollama 等。mock 模式返回一段确定性脚本，无 Key 也能跑通整条循环（学习用）。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finished: bool = False


def is_mock() -> bool:
    return os.environ.get("LLM_MOCK", "1") == "1"


class MockLlm:
    """确定性 mock：把用户指令翻译成固定的工具调用脚本。

    它不联网、不读消息历史，只用内部队列驱动循环；每轮返回一个 tool_call，
    队列空则返回收尾文本。目的是演示「LLM 的决定长什么样」。
    """

    def __init__(self):
        self._steps: list[ToolCall] = []
        self._final_text = ""
        self._seeded = False

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResponse:
        if not self._seeded:
            self._seed(messages)
            self._seeded = True
        if self._steps:
            call = self._steps.pop(0)
            return ChatResponse(tool_calls=[call])
        return ChatResponse(text=self._final_text, finished=True)

    def _seed(self, messages: list[dict]) -> None:
        user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user = m.get("content", "")
                break
        self._steps = [
            ToolCall("t1", "add_clip", {"label": "片段 A", "track": "v1", "start": 0.0, "duration": 3.0}),
            ToolCall("t2", "add_clip", {"label": "片段 B", "track": "v1", "start": 3.0, "duration": 3.0}),
        ]
        has_caption = "字幕" in user or "caption" in user.lower()
        if has_caption:
            self._steps.append(
                ToolCall("t3", "add_caption", {"text": "这是自动生成的字幕", "start": 0.0, "duration": 6.0})
            )
        self._final_text = "已完成：添加了两个片段" + ("，以及一条字幕。" if has_caption else "。")


class OpenAiLlm:
    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI(
            base_url=os.environ.get("LLM_BASE_URL") or None,
            api_key=os.environ.get("LLM_API_KEY") or "not-needed-for-local",
        )
        self._model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResponse:
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages, tools=tools,
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            calls = [
                ToolCall(
                    id=tc.id or f"call_{i}",
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments or "{}"),
                )
                for i, tc in enumerate(msg.tool_calls)
            ]
            return ChatResponse(tool_calls=calls)
        return ChatResponse(text=msg.content or "", finished=True)


def create_llm():
    return MockLlm() if is_mock() else OpenAiLlm()
