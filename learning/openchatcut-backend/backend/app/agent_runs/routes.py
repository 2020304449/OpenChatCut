"""agent-runs HTTP 路由（对齐 server/agent-runs/routes.ts）。

create（延迟执行）+ start + SSE 事件流 + tool-claim + tool-result。
事件经 asyncio.Queue 在 execute_run（后台 task）与 SSE 消费者之间桥接。
"""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..llm import create_llm
from ..persist import data_dir
from .executor import execute_run
from .store import RunStore, approve_tool_request, claim_tool_request, settle_tool_result

router = APIRouter(prefix="/api/agent-runs")

store = RunStore(os.path.join(data_dir(), "agent-runs.sqlite3"))
_event_queues: dict[str, asyncio.Queue] = {}
_tasks: dict[str, asyncio.Task] = {}


class CreateBody(BaseModel):
    message: str
    state: dict
    supportedTools: list[str] | None = None   # 能力协商：browser 声明的工具集


class ClaimBody(BaseModel):
    toolCallId: str
    claimId: str


class ResultBody(BaseModel):
    toolCallId: str
    claimId: str
    argsDigest: str
    result: dict


class ApprovalBody(BaseModel):
    toolCallId: str
    decision: str                # approved | rejected


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _run_loop(run_id: str, message: str, state: dict, q: asyncio.Queue) -> None:
    run = store.get(run_id)
    if run is None:
        return
    llm = create_llm()
    async for ev in execute_run(run, message, llm, state):
        await q.put(ev)
    store.persist(run)  # 结束时落盘（recovery：状态不丢、可审计）
    await q.put(None)  # 结束信号


@router.post("")
async def create(body: CreateBody):
    run = store.create(body.message, body.state, body.supportedTools)
    return {"runId": run.id, "state": run.state}


@router.post("/{run_id}/start")
async def start(run_id: str):
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    q: asyncio.Queue = asyncio.Queue()
    _event_queues[run_id] = q
    _tasks[run_id] = asyncio.create_task(_run_loop(run_id, run.message, run.initial_state or {}, q))
    return {"runId": run_id, "state": "running"}


@router.get("/{run_id}/events")
async def events(run_id: str):
    q = _event_queues.get(run_id)
    if q is None:
        raise HTTPException(404, "run not started")

    async def gen():
        while True:
            ev = await q.get()
            if ev is None:
                break
            yield _sse(ev["event"], ev["data"])

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/{run_id}/tool-claim")
async def tool_claim(run_id: str, body: ClaimBody):
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return claim_tool_request(run, body.toolCallId, body.claimId)


@router.post("/{run_id}/tool-result")
async def tool_result(run_id: str, body: ResultBody):
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return settle_tool_result(run, body.toolCallId, body.claimId, body.argsDigest, body.result)


@router.post("/{run_id}/approval")
async def approval(run_id: str, body: ApprovalBody):
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return approve_tool_request(run, body.toolCallId, body.decision)


@router.get("/{run_id}")
async def get_run(run_id: str):
    """run 摘要 + metrics。"""
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    m = run.metrics
    return {
        "runId": run.id,
        "state": run.state,
        "message": run.message,
        "metrics": {
            "iterations": m.iterations,
            "tool_calls": m.tool_calls,
            "approvals": m.approvals,
            "errors": m.errors,
            "duration_ms": m.duration_ms,
        },
    }
