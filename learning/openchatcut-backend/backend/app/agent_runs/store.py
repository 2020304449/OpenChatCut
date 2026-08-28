"""agent-runs store + claim/settle 协议（对齐 server/agent-runs/store-tools.ts）。

server LLM 循环产出 tool-request 后挂起 wait_for_tool_result，等 browser 经
/tool-claim + /tool-result 结算。三重防护：claimId（claim 归属）、
argsDigest（参数一致性）、outcomeDigest（结算幂等，骨架用 result 幂等代替）。
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field

from ..persist import data_dir
from ..storage.sqlite_store import SqliteStore

SERVER_TOOL_RESULT_TIMEOUT_MS = 120_000
APPROVAL_TIMEOUT_MS = 120_000


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
    status: str = "pending"            # pending | pending_approval | approved | claimed | settled | rejected
    claim_id: str | None = None
    result: dict | None = None
    future: asyncio.Future | None = None            # 工具执行结果的 future（settle 时 set_result）
    approval_future: asyncio.Future | None = None   # 审批决定的 future（approve/reject 时 set_result）


@dataclass
class RunMetrics:
    iterations: int = 0          # LLM 迭代轮数
    tool_calls: int = 0          # 工具调用总次数
    approvals: int = 0           # 审批次数
    errors: int = 0              # LLM/工具错误次数
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    duration_ms: int | None = None


@dataclass
class ServerRun:
    id: str
    message: str = ""
    initial_state: dict | None = None
    state: str = "pending"             # pending | running | done | failed
    tool_requests: dict[str, ServerToolRequest] = field(default_factory=dict)
    metrics: RunMetrics = field(default_factory=RunMetrics)
    supported_tools: list[str] | None = None   # 能力协商：browser 声明的工具集，None=全量


def _run_to_dict(run: ServerRun) -> dict:
    """序列化 run 的数据部分（排除 future，不可序列化）。"""
    return {
        "id": run.id,
        "message": run.message,
        "initial_state": run.initial_state,
        "state": run.state,
        "supported_tools": run.supported_tools,
        "metrics": dataclasses.asdict(run.metrics),
        "tool_requests": {
            tid: {
                "name": req.name,
                "args": req.args,
                "args_digest": req.args_digest,
                "status": req.status,
                "result": req.result,
            }
            for tid, req in run.tool_requests.items()
        },
    }


def _run_from_dict(data: dict) -> ServerRun:
    """反序列化 run 快照（future 不恢复，仅供审计）。"""
    run = ServerRun(
        id=data["id"],
        message=data.get("message", ""),
        initial_state=data.get("initial_state"),
        state=data.get("state", "pending"),
        supported_tools=data.get("supported_tools"),
    )
    run.metrics = RunMetrics(**data.get("metrics", {}))
    for tid, rd in data.get("tool_requests", {}).items():
        run.tool_requests[tid] = ServerToolRequest(
            tool_call_id=tid,
            name=rd["name"],
            args=rd["args"],
            args_digest=rd["args_digest"],
            status=rd["status"],
            result=rd.get("result"),
        )
    return run


class RunStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._runs: dict[str, ServerRun] = {}
        self._db_path = db_path

    def create(self, message: str, initial_state: dict, supported_tools: list[str] | None = None) -> ServerRun:
        run = ServerRun(id=uuid.uuid4().hex[:12], message=message, initial_state=initial_state,
                        supported_tools=supported_tools)
        self._runs[run.id] = run
        self.persist(run)
        return run

    def get(self, run_id: str) -> ServerRun | None:
        return self._runs.get(run_id)

    def persist(self, run: ServerRun) -> None:
        """把 run 快照落盘（SQLite）。db_path 为 None 时不持久化。"""
        if not self._db_path:
            return
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        store = SqliteStore(self._db_path)
        try:
            store.put(f"run:{run.id}", json.dumps(_run_to_dict(run), ensure_ascii=False))
        finally:
            store.close()

    def load(self) -> list[ServerRun]:
        """从 SQLite 恢复 run 快照（供审计，不续跑）。"""
        if not self._db_path or not os.path.exists(self._db_path):
            return []
        store = SqliteStore(self._db_path)
        try:
            runs = []
            for key in store.keys("run:"):
                raw = store.get(key)
                if raw:
                    runs.append(_run_from_dict(json.loads(raw)))
            return runs
        finally:
            store.close()


def register_tool_request(
    run: ServerRun,
    tool_call_id: str,
    name: str,
    args: dict,
    requires_approval: bool = False,
) -> ServerToolRequest:
    """登记 tool request（在 yield tool-request 事件之前调用，确保 settle 能找到）。

    requires_approval=True 时进入 pending_approval 态，先等审批，approved 后才可 claim。
    """
    req = ServerToolRequest(
        tool_call_id=tool_call_id,
        name=name,
        args=args,
        args_digest=args_digest(args),
    )
    req.future = asyncio.get_running_loop().create_future()
    if requires_approval:
        req.status = "pending_approval"
        req.approval_future = asyncio.get_running_loop().create_future()
    run.tool_requests[tool_call_id] = req
    return req


async def await_tool_result(req: ServerToolRequest) -> dict:
    try:
        return await asyncio.wait_for(req.future, timeout=SERVER_TOOL_RESULT_TIMEOUT_MS / 1000)
    except asyncio.TimeoutError:
        return {"ok": False, "error": "tool result timeout"}


async def await_approval(req: ServerToolRequest) -> bool:
    """等审批决定，返回是否 approved（超时视为拒绝）。"""
    if req.approval_future is None:
        return False
    try:
        return await asyncio.wait_for(req.approval_future, timeout=APPROVAL_TIMEOUT_MS / 1000)
    except asyncio.TimeoutError:
        return False


def approve_tool_request(run: ServerRun, tool_call_id: str, decision: str) -> dict:
    """审批决定：decision ∈ {approved, rejected}。"""
    req = run.tool_requests.get(tool_call_id)
    if req is None:
        return {"ok": False, "error": "unknown tool request"}
    if req.status != "pending_approval":
        return {"ok": False, "error": f"not pending approval: {req.status}"}
    if decision == "approved":
        req.status = "approved"
        req.approval_future.set_result(True)
    else:
        req.status = "rejected"
        req.approval_future.set_result(False)
    return {"ok": True, "toolCallId": tool_call_id, "status": req.status}


def claim_tool_request(run: ServerRun, tool_call_id: str, claim_id: str) -> dict:
    req = run.tool_requests.get(tool_call_id)
    if req is None:
        return {"ok": False, "error": "unknown tool request"}
    if req.status not in ("pending", "approved"):   # 审批通过后的 approved 态也可 claim
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
