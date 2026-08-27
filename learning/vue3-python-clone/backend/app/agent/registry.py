"""工具注册表：把工具列表封装成可查询、可执行、可导出 schema 的对象。"""
from __future__ import annotations

from .tools import TOOLS, Tool, ToolContext


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        """导出给 LLM 的工具 schema（OpenAI function-calling 格式）。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict, ctx: ToolContext) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        try:
            args = tool.args_model.model_validate(arguments)
            return tool.execute(args, ctx)
        except Exception as exc:  # LLM 输出不合法时回填可读错误，让模型自我纠正
            return {"ok": False, "error": f"invalid args for {name}: {exc}"}


def build_registry() -> ToolRegistry:
    return ToolRegistry(TOOLS)
