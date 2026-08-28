"""MCP server（对齐 server/external-agent/mcp.ts + mcp-controls.ts）。

OpenChatCut 自身即 MCP server，用官方 mcp SDK（2.x 的 MCPServer）的 Streamable HTTP。
本骨架注册 5 个控制工具（不经 broker，server 直接处理）；编辑工具（browser 上报）
的动态暴露在 arch-4 端到端接线时挂接。
"""
from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from .broker import Broker
from .registry import Registry

broker = Broker()
registry = Registry()


def create_mcp_server() -> MCPServer:
    server = MCPServer("openchatcut")

    @server.tool(name="openchatcut_status", description="查看 OpenChatCut MCP 连接状态")
    async def openchatcut_status() -> str:
        return json.dumps({
            "bindingMode": "browser",
            "availableToolTier": "browser",
            "connectedClients": 1,
        }, ensure_ascii=False)

    @server.tool(name="list_projects", description="列出项目")
    async def list_projects() -> str:
        # 骨架：单项目 default（多项目支持在 arch-4 接 SQLite project store）
        return json.dumps([{"id": "default", "name": "时间线 1"}], ensure_ascii=False)

    @server.tool(name="create_project", description="创建新项目")
    async def create_project(name: str) -> str:
        return json.dumps({"ok": True, "projectId": "default", "name": name}, ensure_ascii=False)

    @server.tool(name="target_project", description="设置目标项目（编辑工具作用域）")
    async def target_project(projectId: str) -> str:
        return json.dumps({"ok": True, "projectId": projectId}, ensure_ascii=False)

    @server.tool(name="get_editor_url", description="获取编辑器 URL")
    async def get_editor_url() -> str:
        return json.dumps({"url": "http://localhost:5173"}, ensure_ascii=False)

    return server
