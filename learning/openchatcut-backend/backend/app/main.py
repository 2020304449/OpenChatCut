"""FastAPI 入口：agent-runs + external MCP 路由挂载。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent_runs.routes import router as agent_runs_router
from .mcp.routes import router as external_agent_router
from .mcp.server import external_mcp_app


app = FastAPI(title="OpenChatCut 后端迁移")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内部 server run 的 claim/settle 协议（arch-3）
app.include_router(agent_runs_router)

# 外部 MCP agent 的 broker 长轮询协议（arch-4）+ Streamable HTTP MCP server
app.include_router(external_agent_router)
app.mount("/api/external-mcp", external_mcp_app())
