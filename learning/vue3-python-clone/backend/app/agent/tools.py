"""Agent 工具面：每个工具 = Pydantic 参数模型 + execute()。

这是「自然语言 → 编辑核心命令」的翻译层，对照 OpenChatCut `src/agent/tools/`
（172 个工具文件）。每个工具的 execute 只做两件事：校验参数 → 发一条 Command。

参数模型用 Pydantic：`model_json_schema()` 直接就是发给 LLM 的工具 schema
（对照 `src/agent/tool-schema.ts` 的 AgentToolSchema），execute 时 `model_validate`
则校验 LLM 的非法输出。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field

from ..editor.commands import AddClip, RemoveClip, SetClipDuration
from ..editor.model import new_id


# ── 参数模型（= 发给 LLM 的工具 schema） ───────────────────────────────────

class ListTimelineArgs(BaseModel):
    pass


class AddClipArgs(BaseModel):
    label: str = Field(..., description="片段名称")
    track: str = Field(..., description="轨道 id：v1（视频）或 c1（字幕）")
    start: float = Field(..., description="起始时间（秒）")
    duration: float = Field(..., description="时长（秒）")
    kind: str = Field(default="video", description="片段类型：video / caption")


class AddCaptionArgs(BaseModel):
    text: str = Field(..., description="字幕文字")
    start: float = Field(..., description="起始时间（秒）")
    duration: float = Field(..., description="时长（秒）")


class SetClipDurationArgs(BaseModel):
    clip_id: str = Field(..., description="目标片段 id")
    duration: float = Field(..., description="新时长（秒）")


class RemoveClipArgs(BaseModel):
    clip_id: str = Field(..., description="目标片段 id")


# ── 工具上下文与工具描述 ───────────────────────────────────────────────────

@dataclass
class ToolContext:
    """execute 的上下文：持有工程仓库，工具通过它发命令。"""
    store: Any  # ProjectStore


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    execute: Callable[[BaseModel, ToolContext], dict]

    @property
    def parameters(self) -> dict:
        return self.args_model.model_json_schema()


# ── 工具实现 ───────────────────────────────────────────────────────────────

def exec_list_timeline(args: ListTimelineArgs, ctx: ToolContext) -> dict:
    return {"ok": True, **ctx.store.to_dict()}


def exec_add_clip(args: AddClipArgs, ctx: ToolContext) -> dict:
    clip_id = new_id()
    ctx.store.apply(AddClip(
        clip_id=clip_id, label=args.label, kind=args.kind,
        track_id=args.track, start=args.start, duration=args.duration,
    ))
    return {"ok": True, "clip_id": clip_id, "label": args.label}


def exec_add_caption(args: AddCaptionArgs, ctx: ToolContext) -> dict:
    clip_id = new_id()
    ctx.store.apply(AddClip(
        clip_id=clip_id, label=args.text, kind="caption",
        track_id="c1", start=args.start, duration=args.duration,
    ))
    return {"ok": True, "caption_id": clip_id, "text": args.text}


def exec_set_clip_duration(args: SetClipDurationArgs, ctx: ToolContext) -> dict:
    ctx.store.apply(SetClipDuration(clip_id=args.clip_id, duration=args.duration))
    return {"ok": True, "clip_id": args.clip_id, "duration": args.duration}


def exec_remove_clip(args: RemoveClipArgs, ctx: ToolContext) -> dict:
    ctx.store.apply(RemoveClip(clip_id=args.clip_id))
    return {"ok": True, "clip_id": args.clip_id}


TOOLS: list[Tool] = [
    Tool("list_timeline", "读取当前时间线（轨道与片段）", ListTimelineArgs, exec_list_timeline),
    Tool("add_clip", "在指定轨道添加一个片段", AddClipArgs, exec_add_clip),
    Tool("add_caption", "在字幕轨添加一条字幕", AddCaptionArgs, exec_add_caption),
    Tool("set_clip_duration", "修改某片段的时长", SetClipDurationArgs, exec_set_clip_duration),
    Tool("remove_clip", "删除某片段", RemoveClipArgs, exec_remove_clip),
]
