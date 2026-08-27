"""FastAPI 入口：REST 端点 + SSE 流。"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agent.loop import run_agent
from .agent.registry import build_registry
from .commands.base import Executor
from .domain.timeline import default_project, project_to_dict
from .llm import create_llm
from .persist import load_project, save_project


executor: Executor = Executor(default_project())


@asynccontextmanager
async def lifespan(app):
    global executor
    loaded = load_project()
    if loaded is not None:
        executor = Executor(loaded)
    yield
    save_project(executor.state)


app = FastAPI(title="OpenChatCut 后端迁移", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatBody(BaseModel):
    message: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def chat(body: ChatBody):
    def gen():
        llm = create_llm()
        for ev in run_agent(body.message, executor, llm):
            yield _sse(ev["event"], ev["data"])

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/state")
def get_state():
    return project_to_dict(executor.state)


@app.get("/api/tools")
def get_tools():
    return build_registry().schemas()


@app.post("/api/undo")
def undo():
    executor.undo()
    return project_to_dict(executor.state)


@app.post("/api/redo")
def redo():
    executor.redo()
    return project_to_dict(executor.state)
