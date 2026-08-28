"""MCP server（对齐 server/external-agent/mcp.ts + mcp-controls.ts）。

OpenChatCut 自身即 MCP server，用官方 mcp SDK（2.x 的 MCPServer）的 Streamable HTTP。
分三类工具：
1. 5 个控制工具（openchatcut_status/list_projects/create_project/target_project/get_editor_url）
   —— 不经 broker，server 直接处理。
2. 编辑/只读工具（agent/tools.py 的 46 个核心工具）—— 经 broker 路由到 browser 执行
   （browser 持有 mutation authority，server 只「选工具 + 传参」）。
3. 生成/导出类工具（generation_tools.py 的 20 个）—— server 端重插件（mock 存根），
   骨架阶段暂不挂到 MCP（其 execute 依赖 ToolContext/Executor，后续 cd 阶段补真实服务时再接）。
"""
from __future__ import annotations

import asyncio
import json
import os

from mcp.server.mcpserver import MCPServer

from ..agent.tools import GENERATION_TOOLS, TOOLS
from ..persist import data_dir
from .broker import CALL_DEADLINE_SECONDS, Broker, EditorBinding
from .registry import Registry

broker = Broker()
registry = Registry(os.path.join(data_dir(), "external-agent.sqlite3"))
registry.load()   # 启动时恢复已注册的 browser 连接

CONTROL_TOOL_NAMES = {
    "openchatcut_status", "list_projects", "create_project",
    "target_project", "get_editor_url",
}
# 生成/导出类工具是 server 端重插件，不经 broker（browser 不持有其执行权）。
GENERATION_TOOL_NAMES = {t.name for t in GENERATION_TOOLS}
DEFAULT_PROJECT = "default"


def _make_edit_tool(name: str):
    """编辑/只读工具：经 broker 路由到 browser（browser 权威）。"""
    async def fn(**kwargs) -> str:
        reg = registry.get(DEFAULT_PROJECT)
        if reg is None:
            return json.dumps({"ok": False, "error": "no editor registered"}, ensure_ascii=False)
        binding = EditorBinding(
            projectId=reg.projectId,
            editorInstanceId=reg.editorInstanceId,
            baseRevision=reg.baseRevision,
            ownershipEpoch=reg.ownershipEpoch,
        )
        fut = broker.invoke(binding, name, kwargs)
        try:
            result = await asyncio.wait_for(fut, timeout=CALL_DEADLINE_SECONDS)
        except asyncio.TimeoutError:
            return json.dumps({"ok": False, "error": "editor call timeout"}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)

    return fn


def create_mcp_server() -> MCPServer:
    server = MCPServer("openchatcut")

    @server.tool(name="openchatcut_status", description="查看 OpenChatCut MCP 连接状态")
    async def openchatcut_status() -> str:
        return json.dumps({
            "bindingMode": "browser",
            "availableToolTier": "browser",
            "connectedClients": len(registry.list()),
        }, ensure_ascii=False)

    @server.tool(name="mcp_check", description="检查 MCP 连接健康状态")
    async def mcp_check() -> str:
        return json.dumps({
            "ok": True,
            "browserOnline": registry.get(DEFAULT_PROJECT) is not None,
            "pendingCalls": broker.pending_count(),
            "registeredProjects": [r.projectId for r in registry.list()],
        }, ensure_ascii=False)

    @server.tool(name="list_projects", description="列出项目")
    async def list_projects() -> str:
        # 骨架：单项目 default（多项目支持在后续接 SQLite project store）
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

    # 编辑/只读工具 → broker。schema 用 **kwargs 宽松签名，参数契约以 browser 上报的
    # 工具目录为准（tool == command，schema 与 browser 同源）。
    for tool in TOOLS:
        if tool.name in CONTROL_TOOL_NAMES or tool.name in GENERATION_TOOL_NAMES:
            continue
        server.add_tool(_make_edit_tool(tool.name), name=tool.name, description=tool.description)

    return server


def external_mcp_app():
    """Streamable HTTP app，挂到 /api/external-mcp/mcp。"""
    return create_mcp_server().streamable_http_app(streamable_http_path="/mcp")
