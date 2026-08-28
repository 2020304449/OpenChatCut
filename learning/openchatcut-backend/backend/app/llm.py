"""LLM 客户端：OpenAI 兼容 + mock 模式，统一流式接口。

真实模式走 openai 官方 SDK 的 base_url 覆盖（OpenAI / DeepSeek / Moonshot / 本地 Ollama）。
mock 模式返回确定性脚本，无 Key 也能跑通整条循环（学习用）。

统一接口 `stream_chat(messages, tools) -> Iterator[dict]`，产出事件：
  {"type": "text", "delta": "..."}          文本增量（token 级）
  {"type": "tool_calls", "calls": [ToolCall]} 本轮的工具调用
  {"type": "done"}                            本轮结束
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


def is_mock() -> bool:
    return os.environ.get("LLM_MOCK", "1") == "1"


class MockLlm:
    """确定性 mock：把用户指令翻译成固定工具调用脚本，演示「LLM 的决定长什么样」。"""

    def __init__(self):
        self._steps: list[ToolCall] = []
        self._final_text = ""
        self._seeded = False

    def stream_chat(self, messages: list[dict], tools: list[dict]):
        if not self._seeded:
            self._seed(messages)
            self._seeded = True
        if self._steps:
            call = self._steps.pop(0)
            yield {"type": "tool_calls", "calls": [call]}
            yield {"type": "done"}
            return
        # 模拟 token 流式：按 2 字符切
        for i in range(0, len(self._final_text), 2):
            yield {"type": "text", "delta": self._final_text[i:i + 2]}
        yield {"type": "done"}

    def _seed(self, messages: list[dict]) -> None:
        user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user = m.get("content", "")
                break
        steps = [
            ToolCall("t1", "add_clip", {"label": "片段 A", "track": "V1", "startFrame": 0, "durationInFrames": 90, "kind": "video"}),
            ToolCall("t2", "add_clip", {"label": "片段 B", "track": "V1", "startFrame": 90, "durationInFrames": 90, "kind": "video"}),
        ]
        extras = []
        if "转场" in user or "transition" in user.lower():
            extras.append(ToolCall("t3", "add_transition",
                                   {"transitionId": "tr1", "incomingItemId": "片段B", "transType": "crossfade", "durationInFrames": 15}))
        if "字幕" in user or "caption" in user.lower():
            extras.append(ToolCall("t4", "edit_captions",
                                   {"action": "set", "enabled": True, "texts": ["这是自动生成的字幕"]}))
        if "生成" in user or "图片" in user or "image" in user.lower():
            extras.append(ToolCall("t5", "submit_image",
                                   {"prompt": "一张科技感封面图", "name": "封面", "count": 1}))
        self._steps = steps + extras
        self._final_text = "已完成：添加了两个片段" + \
            ("，并加了转场" if "转场" in user else "") + \
            ("，以及字幕" if "字幕" in user else "") + \
            ("，以及一张生成图片" if "生成" in user or "图片" in user else "") + "。"


def _is_transient(error: Exception) -> bool:
    """瞬时失败（限流/超时/连接/服务端）才值得重试。"""
    from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
    return isinstance(error, (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError))


class OpenAiLlm:
    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI(
            base_url=os.environ.get("LLM_BASE_URL") or None,
            api_key=os.environ.get("LLM_API_KEY") or "not-needed-for-local",
        )
        self._model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    def stream_chat(self, messages: list[dict], tools: list[dict]):
        # B1: 瞬时失败退避重试（最多 3 次），确定性失败直接抛
        for attempt in range(3):
            try:
                yield from self._stream_once(messages, tools)
                return
            except Exception as exc:
                if attempt == 2 or not _is_transient(exc):
                    raise
                time.sleep(0.5 * (2 ** attempt))   # 500ms → 1s → 2s

    def _stream_once(self, messages: list[dict], tools: list[dict]):
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages, tools=tools, stream=True,
        )
        acc: dict[int, dict] = {}
        for chunk in resp:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                yield {"type": "text", "delta": delta.content}
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index or 0
                    a = acc.setdefault(idx, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        a["id"] = tc.id
                    if tc.function and tc.function.name:
                        a["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        a["args"] += tc.function.arguments
        if acc:
            calls = [
                ToolCall(id=a["id"] or f"call_{i}", name=a["name"],
                         arguments=json.loads(a["args"] or "{}"))
                for i, a in sorted(acc.items())
            ]
            yield {"type": "tool_calls", "calls": calls}
        yield {"type": "done"}


def create_llm():
    return MockLlm() if is_mock() else OpenAiLlm()
