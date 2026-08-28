"""agent-runs store + claim/settle 协议（对齐 server/agent-runs/store-tools.ts）。

server LLM 循环产出 tool-request 后挂起 wait_for_tool_result，等 browser 经
/tool-claim + /tool-result 结算。三重防护：claimId（claim 归属）、
argsDigest（参数一致性）、outcomeDigest（结算幂等，骨架用 result 幂等代替）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass, field

SERVER_TOOL_RESULT_TIMEOUT_MS = 120_000


def args_digest(args: dict) -> str:
    return hashlib.sha256(
        json.dumps(args, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


@dataclass
class ServerToolRequest:
    tool_call_id: str
    name: str
    args: dict
    args_digest: str
    status: str = "pending"            # pending | claimed | settled
    claim_id: str | None = None
    result: dict | None = None
    future: asyncio.Future | None = None


@dataclass
class ServerRun:
    id: str
    message: str = ""
    initial_state: dict | None = None
    state: str = "pending"             # pending | running | done | failed
    tool_requests: dict[str, ServerToolRequest] = field(default_factory=dict)


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, ServerRun] = {}

    def create(self, message: str, initial_state: dict) -> ServerRun:
        run = ServerRun(id=uuid.uuid4().hex[:12], message=message, initial_state=initial_state)
        self._runs[run.id] = run
        return run

    def get(self, run_id: str) -> ServerRun | None:
        return self._runs.get(run_id)


def register_tool_request(run: ServerRun, tool_call_id: str, name: str, args: dict) -> ServerToolRequest:
    """登记 tool request（在 yield tool-request 事件之前调用，确保 settle 能找到）。"""
    req = ServerToolRequest(
        tool_call_id=tool_call_id,
        name=name,
        args=args,
        args_digest=args_digest(args),
    )
    req.future = asyncio.get_running_loop().create_future()
    run.tool_requests[tool_call_id] = req
    return req


async def await_tool_result(req: ServerToolRequest) -> dict:
    try:
        return await asyncio.wait_for(req.future, timeout=SERVER_TOOL_RESULT_TIMEOUT_MS / 1000)
    except asyncio.TimeoutError:
        return {"ok": False, "error": "tool result timeout"}


def claim_tool_request(run: ServerRun, tool_call_id: str, claim_id: str) -> dict:
    req = run.tool_requests.get(tool_call_id)
    if req is None:
        return {"ok": False, "error": "unknown tool request"}
    if req.status != "pending":
        return {"ok": False, "error": f"already {req.status}"}
    req.status = "claimed"
    req.claim_id = claim_id
    return {"ok": True, "toolCallId": tool_call_id}


def settle_tool_result(
    run: ServerRun,
    tool_call_id: str,
    claim_id: str,
    args_digest_value: str,
    result: dict,
) -> dict:
    req = run.tool_requests.get(tool_call_id)
    if req is None:
        return {"ok": False, "error": "unknown tool request"}
    if req.claim_id != claim_id:
        return {"ok": False, "error": "claim mismatch"}
    if req.args_digest != args_digest_value:
        return {"ok": False, "error": "args digest mismatch"}
    req.status = "settled"
    req.result = result
    if req.future and not req.future.done():
        req.future.set_result(result)
    return {"ok": True}
