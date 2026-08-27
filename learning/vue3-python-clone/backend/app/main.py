"""FastAPI 入口：REST 端点 + SSE 流。"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agent.loop import run_agent
from .agent.registry import build_registry
from .editor.store import ProjectStore
from .llm import create_llm

app = FastAPI(title="AI 剪辑智能体 · 最小克隆")

# 前端 dev 走 vite 代理，正常无需 CORS；这里放开以便直接跨端口调试。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = ProjectStore()


class ChatBody(BaseModel):
    message: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def chat(body: ChatBody):
    def gen():
        llm = create_llm()
        for ev in run_agent(body.message, store, llm):
            yield _sse(ev["event"], ev["data"])

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/state")
def get_state():
    return store.to_dict()


@app.get("/api/tools")
def get_tools():
    return build_registry().schemas()


@app.post("/api/undo")
def undo():
    store.undo()
    return store.to_dict()


@app.post("/api/redo")
def redo():
    store.redo()
    return store.to_dict()
