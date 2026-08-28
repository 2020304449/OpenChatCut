"""external-agent HTTP 路由（对齐 server/plugins/external-agent-bridge-routes.ts）。

browser 侧桥接端点：register（注册 + 上报工具，换 registrationCapability）、
poll（长轮询取 broker 队列里的调用）、result（结算 + 回传 baseRevision）。

鉴权：register 返回的 registrationCapability（43 位 base64url）作为后续 poll/result
的请求头 `X-OpenChatCut-Editor-Registration`；baseRevision 用于防漂移。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from .broker import EditorBinding
from .server import broker, registry

router = APIRouter(prefix="/api/external-agent")

CAPABILITY_HEADER = "x-openchatcut-editor-registration"
DEFAULT_PROJECT = "default"


class RegisterBody(BaseModel):
    projectId: str = DEFAULT_PROJECT
    editorId: str
    baseRevision: str
    tools: list[dict] = []


class ResultBody(BaseModel):
    callId: str
    outcome: str                # applied | rejected | cancelled | stale | failed
    result: dict | None = None
    message: str = ""
    baseRevision: str | None = None


class DisconnectBody(BaseModel):
    projectId: str = DEFAULT_PROJECT


def _verify(project_id: str, capability: str | None) -> None:
    if not registry.verify(project_id, capability):
        raise HTTPException(401, "invalid editor registration")


def _binding_for(project_id: str) -> EditorBinding:
    reg = registry.get(project_id)
    if reg is None:
        raise HTTPException(409, "no editor registered for project")
    return EditorBinding(
        projectId=reg.projectId,
        editorInstanceId=reg.editorInstanceId,
        baseRevision=reg.baseRevision,
        ownershipEpoch=reg.ownershipEpoch,
    )


@router.post("/register")
async def register(body: RegisterBody):
    reg = registry.register(
        body.projectId,
        body.editorId,
        body.baseRevision,
        tools=body.tools,
    )
    return {
        "ok": True,
        "projectId": reg.projectId,
        "ownershipEpoch": reg.ownershipEpoch,
        "registrationCapability": reg.capability,
    }


@router.get("/poll")
async def poll(
    projectId: str = Query(DEFAULT_PROJECT),
    x_openchatcut_editor_registration: str | None = Header(default=None, alias=CAPABILITY_HEADER),
):
    _verify(projectId, x_openchatcut_editor_registration)
    call = await broker.next_call(projectId)
    if call is None:
        return {"call": None}
    return {
        "call": {
            "id": call.id,
            "name": call.name,
            "arguments": call.arguments,
            "binding": {
                "projectId": call.binding.projectId,
                "editorInstanceId": call.binding.editorInstanceId,
                "baseRevision": call.binding.baseRevision,
            },
        }
    }


@router.post("/result")
async def result(
    body: ResultBody,
    projectId: str = Query(DEFAULT_PROJECT),
    x_openchatcut_editor_registration: str | None = Header(default=None, alias=CAPABILITY_HEADER),
):
    _verify(projectId, x_openchatcut_editor_registration)
    settled = broker.settle(body.callId, body.outcome, result=body.result, message=body.message)
    if not settled:
        raise HTTPException(404, "unknown call id")
    if body.baseRevision is not None:
        registry.update_revision(projectId, body.baseRevision)
    return {"ok": True}


@router.get("/connections")
async def connections():
    """列出所有已注册的 browser 连接（运维）。"""
    return {
        "connections": [
            {
                "projectId": r.projectId,
                "editorInstanceId": r.editorInstanceId,
                "ownershipEpoch": r.ownershipEpoch,
                "toolNames": r.toolNames,
            }
            for r in registry.list()
        ]
    }


@router.post("/disconnect")
async def disconnect(body: DisconnectBody):
    """断开某个 project 的 browser 连接（运维）。"""
    registry.unregister(body.projectId)
    return {"ok": True, "projectId": body.projectId}
