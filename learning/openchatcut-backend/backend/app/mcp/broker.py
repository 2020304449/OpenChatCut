"""MCP broker：长轮询 + 状态机（对齐 server/external-agent/broker.ts）。

核心语义：外部 MCP 客户端调用编辑工具 → invoke 入队（queued）→ browser 长轮询
next_call 取走（in_flight）→ browser 结算 settle（applied/stale/cancelled/rejected/failed）。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

CALL_DEADLINE_SECONDS = 180          # 可上调至 600
EDITOR_POLL_BUDGET_SECONDS = 25.0
EDITOR_POLL_REFRESH_SECONDS = 8.0

OUTCOMES = ("applied", "rejected", "cancelled", "stale", "failed")


class ExternalEditorCallError(Exception):
    def __init__(self, outcome: str, message: str = ""):
        self.outcome = outcome
        self.message = message
        super().__init__(f"{outcome}: {message}")


@dataclass
class EditorBinding:
    projectId: str
    editorInstanceId: str
    baseRevision: str
    ownershipEpoch: int | None = None


@dataclass
class QueuedCall:
    id: str
    binding: EditorBinding
    name: str
    arguments: dict
    state: str = "queued"                 # queued | in_flight
    allowRevisionDrift: bool = False
    deadline: float = 0.0
    _resolve: Any = None
    _reject: Any = None


class Broker:
    def __init__(self) -> None:
        self._queues: dict[str, list[QueuedCall]] = {}
        self._pending: dict[str, QueuedCall] = {}
        self._waiters: dict[str, list[asyncio.Future]] = {}

    # ── server 侧：入队并挂起 ─────────────────────────────────────────────

    def invoke(
        self,
        binding: EditorBinding,
        name: str,
        arguments: dict,
        allow_revision_drift: bool = False,
    ) -> "asyncio.Future":
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        call = QueuedCall(
            id=uuid.uuid4().hex[:16],
            binding=binding,
            name=name,
            arguments=arguments,
            deadline=time.monotonic() + CALL_DEADLINE_SECONDS,
            allowRevisionDrift=allow_revision_drift,
            _resolve=fut.set_result,
            _reject=fut.set_exception,
        )
        self._queues.setdefault(binding.projectId, []).append(call)
        self._pending[call.id] = call
        self._wake(binding.projectId)
        return fut

    # ── browser 侧：长轮询取调用 ─────────────────────────────────────────

    async def next_call(self, project_id: str) -> QueuedCall | None:
        while True:
            q = self._queues.get(project_id, [])
            # 过滤过期的（stale）
            live = [c for c in q if time.monotonic() < c.deadline]
            self._queues[project_id] = live
            if live:
                call = live.pop(0)
                call.state = "in_flight"
                return call
            # 空队列 → 长轮询等待唤醒
            loop = asyncio.get_event_loop()
            waiter: asyncio.Future = loop.create_future()
            self._waiters.setdefault(project_id, []).append(waiter)
            try:
                await asyncio.wait_for(waiter, timeout=EDITOR_POLL_BUDGET_SECONDS)
            except asyncio.TimeoutError:
                return None

    # ── browser 侧：结算 ─────────────────────────────────────────────────

    def settle(self, call_id: str, outcome: str, result: Any = None, message: str = "") -> bool:
        call = self._pending.pop(call_id, None)
        if call is None:
            return False
        self._wake(call.binding.projectId)
        if outcome == "applied":
            call._resolve(result)
        else:
            call._reject(ExternalEditorCallError(outcome, message))
        return True

    def cancel(self, call_id: str, message: str = "cancelled") -> bool:
        return self.settle(call_id, "cancelled", message=message)

    # ── 内部 ─────────────────────────────────────────────────────────────

    def _wake(self, project_id: str) -> None:
        waiters = self._waiters.pop(project_id, [])
        for w in waiters:
            if not w.done():
                w.set_result(None)

    def pending_count(self) -> int:
        """未结算的在途调用数（mcp_check 用）。"""
        return len(self._pending)
