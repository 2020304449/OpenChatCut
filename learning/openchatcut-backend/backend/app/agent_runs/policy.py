"""工具执行策略（对齐 server/agent-runs/tool-policy.ts 的最小实现）。

把工具分为三类，决定执行策略：
- read      只读（read_* 前缀），走 claim/settle，无需审批
- edit      编辑，走 claim/settle，无需审批
- high-risk 生成/导出，claim/settle 前需人工审批

browser 权威不变：策略只决定「是否需要审批」，执行仍在浏览器 claim/settle。
"""
from __future__ import annotations

from typing import Literal

ToolClass = Literal["read", "edit", "high-risk"]

# 高风险工具：生成类（消耗资源/外部服务）+ 导出类（产生文件/FFmpeg）。
# 显式集合而非按前缀派生，因为 generation_tools 里 transcribe_track/probe_media
# 是服务/只读，不算 high-risk。
HIGH_RISK_TOOLS: frozenset[str] = frozenset({
    # 生成类
    "submit_image",
    "submit_voice",
    "submit_sound",
    "submit_music",
    "submit_video",
    "submit_motion_graphic",
    "create_motion_graphic_from_code",
    "submit_shader",
    # 导出类
    "submit_export",
    "submit_render_job",
    "export_motion_graphic_prores",
    "convert_motion_graphic_to_video",
    "export_jianying_draft",
})


def classify(name: str) -> ToolClass:
    if name.startswith("read_"):
        return "read"
    if name in HIGH_RISK_TOOLS:
        return "high-risk"
    return "edit"


def requires_approval(name: str) -> bool:
    return classify(name) == "high-risk"
