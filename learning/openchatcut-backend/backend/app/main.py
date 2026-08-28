"""FastAPI 入口：agent-runs + external MCP + 项目持久化路由挂载。"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent_runs.routes import router as agent_runs_router
from .export_routes import router as export_router
from .mcp.routes import router as external_agent_router
from .mcp.server import external_mcp_app
from .persist import data_dir
from .project_routes import router as project_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时确保 data 目录就绪（SQLite/迁移在首次 save/load 时惰性建表）
    os.makedirs(data_dir(), exist_ok=True)
    yield


app = FastAPI(title="OpenChatCut 后端迁移", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内部 server run 的 claim/settle 协议（arch-3）
app.include_router(agent_runs_router)

# 前端「导出」按钮的渲染端点（browser 权威 state → FFmpeg 成品）
app.include_router(export_router)

# 项目持久化端点（browser 权威 state → SQLite 落盘）
app.include_router(project_router)

# 外部 MCP agent 的 broker 长轮询协议（arch-4）+ Streamable HTTP MCP server
app.include_router(external_agent_router)
app.mount("/api/external-mcp", external_mcp_app())
