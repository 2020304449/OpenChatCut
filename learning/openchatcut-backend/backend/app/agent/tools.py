"""工具面：工具 = 命令（tool == command，对齐 OpenChatCut 的契约）。

每个工具 = Pydantic 参数模型 + execute()。execute 只做「校验参数 → 发命令 → 返回可读结果」。
工具 schema 经 model_json_schema() 导出给 LLM（对齐 src/agent/tool-schema.ts 的 AgentToolSchema）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Literal

from pydantic import BaseModel, Field

from ..commands import actions as A
from ..commands import multicam_actions as MA
from ..commands import project_actions as P
from ..commands import transcript_actions as TA
from ..commands.base import Executor
from ..domain.captions import CaptionCue, CaptionsData
from ..domain.item import ClipEffect, TimelineItem
from ..domain.marker import Marker
from ..domain.media import MediaAsset, MediaFolder
from ..domain.multicam import MulticamAngle, MulticamGroup, TimelineLinkGroup
from ..domain.timeline import Timeline, active_timeline, project_to_dict, timeline_to_dict
from ..domain.transcript import TranscriptVariant, TranscriptVariantWord, TranscriptWord
from ..domain.transition import TransitionItem


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


# [DEFERRED] 生成/导出类工具（依赖外部服务/渲染引擎，后续阶段补充）。
# 统一标记，grep "DEFERRED" 可找到全部延后项，详见 prd.md Out of Scope。
DEFERRED_TOOLS = (
    # 生成类（外部付费服务：DALL-E/TTS/音乐/视频生成）
    "submit_image", "submit_voice", "submit_sound", "submit_music", "submit_video",
    "submit_motion_graphic", "create_motion_graphic_from_code", "submit_shader",
    "track_progress", "rerun_generation",
    # 导出类（渲染引擎 Remotion/FFmpeg，阶段 C/D）
    "submit_export", "submit_render_job", "track_export", "verify_export",
    "export_motion_graphic_prores", "register_converted_video",
    "convert_motion_graphic_to_video", "export_jianying_draft",
)


def _missing_item(executor: Executor, item_id: str) -> dict | None:
    """目标片段不存在时返回错误 dict，存在则返回 None。"""
    tl = active_timeline(executor.state)
    if not any(i.id == item_id for i in tl.items):
        return {"ok": False, "error": f"item not found: {item_id}"}
    return None


# ── 工具上下文与描述 ───────────────────────────────────────────────────────

@dataclass
class ToolContext:
    executor: Executor


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    execute: Callable[[BaseModel, ToolContext], dict]

    @property
    def parameters(self) -> dict:
        return self.args_model.model_json_schema()


# ── 只读工具 ───────────────────────────────────────────────────────────────

class ReadTimelineArgs(BaseModel):
    pass


class ReadProjectArgs(BaseModel):
    pass


def exec_read_timeline(args: ReadTimelineArgs, ctx: ToolContext) -> dict:
    tl = active_timeline(ctx.executor.state)
    return {"ok": True, **timeline_to_dict(tl)}


def exec_read_project(args: ReadProjectArgs, ctx: ToolContext) -> dict:
    doc = ctx.executor.state
    return {
        "ok": True,
        "activeTimelineId": doc.activeTimelineId,
        "timelines": [{"id": t.id, "name": t.name, "items": len(t.items)} for t in doc.timelines],
        "assetCount": len(doc.assets),
    }


# ── 轨道 ───────────────────────────────────────────────────────────────────

class EditTrackArgs(BaseModel):
    action: Literal["create", "update", "delete", "toggle", "tighten"] = Field(..., description="操作类型")
    track: str = Field(..., description="轨道 id，如 V2/A1/C1")
    kind: str | None = Field(None, description="轨道类型：video/audio/caption（create 用）")
    name: str | None = Field(None, description="轨道名")
    flag: Literal["hidden", "muted", "locked", "collapsed"] | None = Field(None, description="toggle 的旗标")
    value: bool | None = Field(None, description="toggle 的值")
    patch: dict | None = Field(None, description="update 的字段补丁")


def exec_edit_track(args: EditTrackArgs, ctx: ToolContext) -> dict:
    ex = ctx.executor
    if args.action == "create":
        if not args.kind:
            return {"ok": False, "error": "create 需要 kind"}
        ex.execute(A.TrackCreate(args.track, args.kind, name=args.name))
        return {"ok": True, "track": args.track, "action": "create"}
    if args.action == "update":
        ex.execute(A.TrackUpdate(args.track, args.patch or {}))
        return {"ok": True, "track": args.track, "action": "update"}
    if args.action == "delete":
        ex.execute(A.TrackDelete(args.track))
        return {"ok": True, "track": args.track, "action": "delete"}
    if args.action == "toggle":
        if not args.flag:
            return {"ok": False, "error": "toggle 需要 flag"}
        ex.execute(A.ToggleTrackFlag(args.track, args.flag, bool(args.value)))
        return {"ok": True, "track": args.track, "flag": args.flag}
    if args.action == "tighten":
        ex.execute(MA.TrackTighten(args.track))
        return {"ok": True, "track": args.track, "action": "tighten"}
    return {"ok": False, "error": f"unknown action: {args.action}"}


# ── 片段基础 ───────────────────────────────────────────────────────────────

class AddClipArgs(BaseModel):
    label: str = Field(..., description="片段名称")
    track: str = Field("V1", description="轨道 id")
    startFrame: int = Field(..., description="起始帧")
    durationInFrames: int = Field(..., description="时长（帧）")
    kind: str = Field("video", description="类型：video/audio/image/text/motion-graphic 等")
    src: str | None = Field(None, description="媒体源")


class RemoveClipArgs(BaseModel):
    itemId: str = Field(..., description="片段 id")


class DuplicateClipArgs(BaseModel):
    itemId: str = Field(..., description="片段 id")


class SplitClipArgs(BaseModel):
    itemId: str = Field(..., description="片段 id")
    atFrame: int = Field(..., description="绝对帧分割点")


class MoveClipArgs(BaseModel):
    itemId: str = Field(..., description="片段 id")
    track: str | None = Field(None, description="目标轨道")
    startFrame: int | None = Field(None, description="目标起始帧")


class SetClipTimingArgs(BaseModel):
    itemId: str = Field(..., description="片段 id")
    startFrame: int | None = Field(None, description="起始帧")
    durationInFrames: int | None = Field(None, description="时长（帧）")
    srcInFrame: int | None = Field(None, description="源入点（帧）")


class UpdateClipPropsArgs(BaseModel):
    itemId: str = Field(..., description="片段 id")
    patch: dict = Field(..., description="要更新的字段（name/props 等）")


class ClearTimelineArgs(BaseModel):
    pass


def exec_add_clip(args: AddClipArgs, ctx: ToolContext) -> dict:
    item = TimelineItem(id=_new_id(), track=args.track, startFrame=args.startFrame,
                        durationInFrames=args.durationInFrames, name=args.label,
                        kind=args.kind, src=args.src)
    ctx.executor.execute(A.AddItem(item))
    return {"ok": True, "itemId": item.id, "label": args.label}


def exec_remove_clip(args: RemoveClipArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.RemoveItem(args.itemId))
    return {"ok": True, "itemId": args.itemId}


def exec_clear_timeline(args: ClearTimelineArgs, ctx: ToolContext) -> dict:
    ctx.executor.execute(A.ClearTimeline())
    return {"ok": True}


def exec_duplicate_clip(args: DuplicateClipArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    new_id = _new_id()
    ctx.executor.execute(A.DuplicateItem(args.itemId, new_id))
    return {"ok": True, "itemId": new_id}


def exec_split_clip(args: SplitClipArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    new_id = _new_id()
    ctx.executor.execute(A.SplitItem(args.itemId, args.atFrame, new_id))
    return {"ok": True, "itemId": new_id, "atFrame": args.atFrame}


def exec_move_clip(args: MoveClipArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.MoveItem(args.itemId, track=args.track, startFrame=args.startFrame))
    return {"ok": True, "itemId": args.itemId}


def exec_set_clip_timing(args: SetClipTimingArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.RetimeItem(args.itemId, startFrame=args.startFrame,
                                      durationInFrames=args.durationInFrames,
                                      srcInFrame=args.srcInFrame))
    return {"ok": True, "itemId": args.itemId}


def exec_update_clip_props(args: UpdateClipPropsArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.UpdateItemProps(args.itemId, args.patch))
    return {"ok": True, "itemId": args.itemId}


# ── 片段属性 ───────────────────────────────────────────────────────────────

class SetClipVolumeArgs(BaseModel):
    itemId: str
    volume: float = Field(..., description="0..1 音量")


class SetClipFadeArgs(BaseModel):
    itemId: str
    fadeInFrames: int | None = None
    fadeOutFrames: int | None = None


class SetClipTransformArgs(BaseModel):
    itemId: str
    patch: dict = Field(..., description="变换字段：scale/x/y/rotation/opacity 等")


class SetClipFiltersArgs(BaseModel):
    itemId: str
    patch: dict = Field(..., description="滤镜字段：brightness/contrast/saturate/blur")


class SetClipSpeedArgs(BaseModel):
    itemId: str
    rate: float = Field(..., description="播放速率，1=正常，2=2倍")


class SetClipZoomArgs(BaseModel):
    itemId: str
    patch: dict = Field(..., description="缩放字段：magnification/shape 等")


class SetClipEffectsArgs(BaseModel):
    itemId: str
    effects: list[dict] = Field(..., description="特效列表：[{id, assetId, overrides?}]")


def exec_set_clip_volume(args: SetClipVolumeArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetItemVolume(args.itemId, args.volume))
    return {"ok": True, "itemId": args.itemId}


def exec_set_clip_fade(args: SetClipFadeArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetItemFade(args.itemId, args.fadeInFrames, args.fadeOutFrames))
    return {"ok": True, "itemId": args.itemId}


def exec_set_clip_transform(args: SetClipTransformArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetItemTransform(args.itemId, args.patch))
    return {"ok": True, "itemId": args.itemId}


def exec_set_clip_filters(args: SetClipFiltersArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetItemFilters(args.itemId, args.patch))
    return {"ok": True, "itemId": args.itemId}


def exec_set_clip_speed(args: SetClipSpeedArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetItemSpeed(args.itemId, args.rate))
    return {"ok": True, "itemId": args.itemId}


def exec_set_clip_zoom(args: SetClipZoomArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetItemZoom(args.itemId, args.patch))
    return {"ok": True, "itemId": args.itemId}


def exec_set_clip_effects(args: SetClipEffectsArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    effects = tuple(ClipEffect(id=e["id"], assetId=e["assetId"], overrides=e.get("overrides"))
                    for e in args.effects)
    ctx.executor.execute(A.SetItemEffects(args.itemId, effects))
    return {"ok": True, "itemId": args.itemId}


# ── 转场 ───────────────────────────────────────────────────────────────────

class AddTransitionArgs(BaseModel):
    transType: str = Field(..., description="转场类型，如 crossfade")
    durationInFrames: int | None = Field(None, description="时长（帧）")
    incomingItemId: str | None = Field(None, description="作用于的片段 id（缺省用最后一个片段）")
    transitionId: str | None = Field(None, description="转场 id（缺省自动生成）")


class EditTransitionArgs(BaseModel):
    action: Literal["update", "remove"] = Field(..., description="操作类型")
    transitionId: str = Field(..., description="转场 id")
    patch: dict | None = Field(None, description="update 的字段补丁")


def exec_add_transition(args: AddTransitionArgs, ctx: ToolContext) -> dict:
    tl = active_timeline(ctx.executor.state)
    incoming = args.incomingItemId
    if not incoming or not any(i.id == incoming for i in tl.items):
        incoming = tl.items[-1].id if tl.items else None
    if not incoming:
        return {"ok": False, "error": "时间线为空，无法加转场"}
    tr = TransitionItem(id=args.transitionId or _new_id(), incomingItemId=incoming,
                        transType=args.transType, durationInFrames=args.durationInFrames)
    ctx.executor.execute(A.AddTransition(tr))
    return {"ok": True, "transitionId": tr.id, "incomingItemId": incoming}


def exec_edit_transition(args: EditTransitionArgs, ctx: ToolContext) -> dict:
    if args.action == "update":
        ctx.executor.execute(A.SetTransition(args.transitionId, args.patch or {}))
    else:
        ctx.executor.execute(A.RemoveTransition(args.transitionId))
    return {"ok": True, "transitionId": args.transitionId}


# ── 字幕 ───────────────────────────────────────────────────────────────────

class EditCaptionsArgs(BaseModel):
    action: Literal["set", "update", "set_hidden"] = Field(..., description="操作类型")
    enabled: bool | None = Field(None, description="是否启用（set/update）")
    texts: list[str] | None = Field(None, description="字幕文本列表（set 用，每条约 90 帧）")
    hidden: bool | None = Field(None, description="是否隐藏（set_hidden）")


def exec_edit_captions(args: EditCaptionsArgs, ctx: ToolContext) -> dict:
    ex = ctx.executor
    if args.action == "set":
        cues = tuple(
            CaptionCue(startFrame=i * 90, endFrame=(i + 1) * 90, text=t)
            for i, t in enumerate(args.texts or [])
        )
        ex.execute(A.SetCaptions(CaptionsData(enabled=(args.enabled is not False), items=cues)))
        return {"ok": True, "count": len(cues)}
    if args.action == "update":
        patch = {}
        if args.enabled is not None:
            patch["enabled"] = args.enabled
        ex.execute(A.UpdateCaptions(patch))
        return {"ok": True}
    if args.action == "set_hidden":
        ex.execute(A.SetCaptionsHidden(bool(args.hidden)))
        return {"ok": True, "hidden": args.hidden}
    return {"ok": False, "error": f"unknown action: {args.action}"}


# ── 关键帧 ─────────────────────────────────────────────────────────────────

class SetKeyframeArgs(BaseModel):
    itemId: str
    prop: str = Field(..., description="属性：x/y/scale/rotation/opacity/volume 等")
    frame: int
    value: float
    easing: str | None = None


class RemoveKeyframeArgs(BaseModel):
    itemId: str
    prop: str
    frame: int


class ClearKeyframesArgs(BaseModel):
    itemId: str
    prop: str | None = None


def exec_set_keyframe(args: SetKeyframeArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetKeyframe(args.itemId, args.prop, args.frame, args.value, args.easing))
    return {"ok": True, "itemId": args.itemId, "prop": args.prop}


def exec_remove_keyframe(args: RemoveKeyframeArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.RemoveKeyframe(args.itemId, args.prop, args.frame))
    return {"ok": True, "itemId": args.itemId}


def exec_clear_keyframes(args: ClearKeyframesArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.ClearKeyframes(args.itemId, args.prop))
    return {"ok": True, "itemId": args.itemId}


# ── 标记 ───────────────────────────────────────────────────────────────────

class ManageMarkersArgs(BaseModel):
    action: Literal["add", "update", "remove"] = Field(..., description="操作类型")
    markerId: str | None = Field(None, description="标记 id")
    name: str | None = Field(None, description="标记名")
    frame: int | None = Field(None, description="点标记的帧")
    color: str | None = Field(None, description="颜色")
    patch: dict | None = Field(None, description="update 的补丁")


def exec_manage_markers(args: ManageMarkersArgs, ctx: ToolContext) -> dict:
    ex = ctx.executor
    if args.action == "add":
        m = Marker(id=args.markerId or _new_id(), name=args.name or "", frame=args.frame, color=args.color)
        ex.execute(A.AddMarker(m))
        return {"ok": True, "markerId": m.id}
    if args.action == "update":
        ex.execute(A.UpdateMarker(args.markerId or "", args.patch or {}))
        return {"ok": True, "markerId": args.markerId}
    if args.action == "remove":
        ex.execute(A.RemoveMarker(args.markerId or ""))
        return {"ok": True, "markerId": args.markerId}
    return {"ok": False, "error": f"unknown action: {args.action}"}


# ── 选择 ───────────────────────────────────────────────────────────────────

class SelectClipsArgs(BaseModel):
    action: Literal["select", "select_many", "select_all"] = Field(..., description="操作类型")
    itemId: str | None = Field(None, description="select 的片段 id")
    ids: list[str] | None = Field(None, description="select_many 的片段 id 列表")
    mode: str = Field("replace", description="select 的模式：replace/toggle/add")


def exec_select_clips(args: SelectClipsArgs, ctx: ToolContext) -> dict:
    ex = ctx.executor
    if args.action == "select":
        ex.execute(A.Select(args.itemId, args.mode))
    elif args.action == "select_many":
        ex.execute(A.SelectMany(tuple(args.ids or [])))
    else:
        ex.execute(A.SelectAll())
    return {"ok": True}


# ── 素材池 ─────────────────────────────────────────────────────────────────

class ManageMediaPoolArgs(BaseModel):
    action: Literal["add_asset", "create_folder", "move_assets", "remove_asset"] = Field(..., description="操作类型")
    assetId: str | None = Field(None, description="资产 id")
    name: str | None = Field(None, description="资产/文件夹名")
    kind: str | None = Field(None, description="资产类型")
    src: str | None = Field(None, description="资产源")
    folderId: str | None = Field(None, description="目标文件夹")
    ids: list[str] | None = Field(None, description="move_assets 的资产 id 列表")


def exec_manage_media_pool(args: ManageMediaPoolArgs, ctx: ToolContext) -> dict:
    ex = ctx.executor
    if args.action == "add_asset":
        a = MediaAsset(id=args.assetId or _new_id(), name=args.name or "", kind=args.kind or "video", src=args.src or "")
        ex.execute(A.AddAsset(a))
        return {"ok": True, "assetId": a.id}
    if args.action == "create_folder":
        f = MediaFolder(id=_new_id(), name=args.name or "")
        ex.execute(A.PoolCreateFolder(f))
        return {"ok": True, "folderId": f.id}
    if args.action == "move_assets":
        ex.execute(A.PoolMoveAssets(tuple(args.ids or []), args.folderId))
        return {"ok": True}
    if args.action == "remove_asset":
        ex.execute(A.PoolRemoveAsset(args.assetId or ""))
        return {"ok": True, "assetId": args.assetId}
    return {"ok": False, "error": f"unknown action: {args.action}"}


# ── 撤销/重做 ──────────────────────────────────────────────────────────────

class UndoArgs(BaseModel):
    pass


class RedoArgs(BaseModel):
    pass


def exec_undo(args: UndoArgs, ctx: ToolContext) -> dict:
    result = ctx.executor.undo()
    if result is None:
        return {"ok": False, "error": "没有可撤销的操作"}
    return {"ok": True, **project_to_dict(result)}


def exec_redo(args: RedoArgs, ctx: ToolContext) -> dict:
    result = ctx.executor.redo()
    if result is None:
        return {"ok": False, "error": "没有可重做的操作"}
    return {"ok": True, **project_to_dict(result)}


# ── 文本稿（A-2） ──────────────────────────────────────────────────────────

class SetItemTranscriptArgs(BaseModel):
    itemId: str
    words: list[dict] = Field(..., description="词列表：[{text, startMs, endMs, speaker?}]")
    generationId: str | None = None


class ReadTranscriptArgs(BaseModel):
    itemId: str


class CleanScriptArgs(BaseModel):
    itemId: str
    removeFillers: bool = True
    silenceFrames: int | None = None
    cutPadFrames: int | None = None


class DeleteTextArgs(BaseModel):
    itemId: str
    wordIndices: list[int] = Field(..., description="要删除的词索引")


class ManageTranscriptArgs(BaseModel):
    action: Literal["fix_word", "rename_speaker", "set_variants"] = Field(..., description="操作类型")
    itemId: str
    wordIndex: int | None = None
    text: str | None = None
    fromSpeaker: str | None = None
    toSpeaker: str | None = None
    variants: list[dict] | None = None


def _words_from(args: list[dict]) -> tuple[TranscriptWord, ...]:
    return tuple(
        TranscriptWord(text=w.get("text", ""), startMs=w.get("startMs", 0),
                       endMs=w.get("endMs", 0), speaker=w.get("speaker"))
        for w in args
    )


def exec_set_item_transcript(args: SetItemTranscriptArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    words = _words_from(args.words)
    ctx.executor.execute(TA.SetItemTranscript(args.itemId, words, args.generationId))
    return {"ok": True, "itemId": args.itemId, "count": len(words)}


def exec_read_transcript(args: ReadTranscriptArgs, ctx: ToolContext) -> dict:
    tl = active_timeline(ctx.executor.state)
    item = next((i for i in tl.items if i.id == args.itemId), None)
    if item is None:
        return {"ok": False, "error": f"item not found: {args.itemId}"}
    words = [{"text": w.text, "startMs": w.startMs, "endMs": w.endMs, "speaker": w.speaker}
             for w in (item.transcript or ())]
    return {"ok": True, "transcript": words, "deletedWordIdx": list(item.deletedWordIdx)}


def exec_clean_script(args: CleanScriptArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(TA.CleanScript(args.itemId, args.removeFillers,
                                        args.silenceFrames, args.cutPadFrames))
    return {"ok": True, "itemId": args.itemId}


def exec_delete_text(args: DeleteTextArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(TA.DeleteWords(args.itemId, tuple(args.wordIndices)))
    return {"ok": True, "itemId": args.itemId}


def exec_manage_transcript(args: ManageTranscriptArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    if args.action == "fix_word":
        ctx.executor.execute(TA.FixTranscriptWord(args.itemId, args.wordIndex or 0, args.text or ""))
        return {"ok": True, "itemId": args.itemId}
    if args.action == "rename_speaker":
        ctx.executor.execute(TA.RenameSpeaker(args.itemId, args.fromSpeaker or "", args.toSpeaker or ""))
        return {"ok": True, "itemId": args.itemId}
    if args.action == "set_variants":
        variants = tuple(
            TranscriptVariant(id=v.get("id", _new_id()), lang=v.get("lang", ""),
                              kind=v.get("kind", "translation"), label=v.get("label", ""),
                              words=tuple(TranscriptVariantWord(i=w["i"], text=w["text"]) for w in v.get("words", [])))
            for v in (args.variants or [])
        )
        ctx.executor.execute(TA.SetItemVariants(args.itemId, variants))
        return {"ok": True, "itemId": args.itemId}
    return {"ok": False, "error": f"unknown action: {args.action}"}


# ── 片段属性补充（A-2） ────────────────────────────────────────────────────

class SlipItemArgs(BaseModel):
    itemId: str
    deltaInFrames: int


class SetBackgroundFillArgs(BaseModel):
    itemId: str
    enabled: bool
    strength: int | None = None


class ReplaceMediaArgs(BaseModel):
    itemId: str
    src: str


class UpdateWatermarkArgs(BaseModel):
    enabled: bool | None = None
    text: str | None = None
    position: str | None = None
    opacity: float | None = None


class SetItemDenoiseArgs(BaseModel):
    itemId: str
    denoisedSrc: str | None
    strength: int | None = None


class SetReframeKeyframeArgs(BaseModel):
    itemId: str
    frame: int
    focalPointX: float
    focalPointY: float
    magnification: float


def exec_slip_item(args: SlipItemArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SlipItem(args.itemId, args.deltaInFrames))
    return {"ok": True, "itemId": args.itemId}


def exec_set_background_fill(args: SetBackgroundFillArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetBackgroundFill(args.itemId, args.enabled, args.strength))
    return {"ok": True, "itemId": args.itemId}


def exec_replace_media(args: ReplaceMediaArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.ReplaceMedia(args.itemId, args.src))
    return {"ok": True, "itemId": args.itemId}


def exec_update_watermark(args: UpdateWatermarkArgs, ctx: ToolContext) -> dict:
    ctx.executor.execute(A.UpdateWatermark(args.enabled, args.text, args.position, args.opacity))
    return {"ok": True}


def exec_set_item_denoise(args: SetItemDenoiseArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetItemDenoise(args.itemId, args.denoisedSrc, args.strength))
    return {"ok": True, "itemId": args.itemId}


def exec_set_reframe_keyframe(args: SetReframeKeyframeArgs, ctx: ToolContext) -> dict:
    if err := _missing_item(ctx.executor, args.itemId):
        return err
    ctx.executor.execute(A.SetReframeKeyframe(args.itemId, args.frame, args.focalPointX,
                                              args.focalPointY, args.magnification))
    return {"ok": True, "itemId": args.itemId}


# ── 项目级（A-2） ──────────────────────────────────────────────────────────

class ManageTimelinesArgs(BaseModel):
    action: Literal["create", "switch", "duplicate", "delete", "rename", "retarget", "set_hidden"] = Field(..., description="操作类型")
    timelineId: str | None = None
    name: str | None = None
    width: int | None = None
    height: int | None = None
    hidden: bool | None = None


class EditMediaPoolArgs(BaseModel):
    action: Literal["rename_folder", "delete_folder", "update_asset", "relink_asset", "canonicalize_asset"] = Field(..., description="操作类型")
    folderId: str | None = None
    assetId: str | None = None
    canonicalId: str | None = None
    name: str | None = None
    src: str | None = None
    patch: dict | None = None


class SetDesignStyleArgs(BaseModel):
    action: Literal["set", "patch"] = Field("set", description="操作类型")
    style: dict | None = None
    patch: dict | None = None


class SetFullStateArgs(BaseModel):
    patch: dict = Field(..., description="要整体更新的状态字段")


def exec_manage_timelines(args: ManageTimelinesArgs, ctx: ToolContext) -> dict:
    ex = ctx.executor
    if args.action == "create":
        tl = Timeline(id=_new_id(), name=args.name or "新时间线", order=len(ex.state.timelines))
        ex.execute(P.TimelineCreate(tl, activate=False))
        return {"ok": True, "timelineId": tl.id}
    if args.action == "switch":
        ex.execute(P.TimelineSwitch(args.timelineId or ""))
        return {"ok": True, "timelineId": args.timelineId}
    if args.action == "duplicate":
        new_id = _new_id()
        ex.execute(P.TimelineDuplicate(args.timelineId or "", new_id, args.name or "副本"))
        return {"ok": True, "timelineId": new_id}
    if args.action == "delete":
        ex.execute(P.TimelineDelete(args.timelineId or ""))
        return {"ok": True, "timelineId": args.timelineId}
    if args.action == "rename":
        ex.execute(P.TimelineRename(args.timelineId or "", args.name or ""))
        return {"ok": True, "timelineId": args.timelineId}
    if args.action == "retarget":
        ex.execute(P.TimelineRetarget(args.timelineId or "", args.width or 1920, args.height or 1080))
        return {"ok": True, "timelineId": args.timelineId}
    if args.action == "set_hidden":
        ex.execute(P.TimelineSetHidden(args.timelineId or "", bool(args.hidden)))
        return {"ok": True, "timelineId": args.timelineId}
    return {"ok": False, "error": f"unknown action: {args.action}"}


def exec_edit_media_pool(args: EditMediaPoolArgs, ctx: ToolContext) -> dict:
    ex = ctx.executor
    if args.action == "rename_folder":
        ex.execute(P.PoolRenameFolder(args.folderId or "", args.name or ""))
        return {"ok": True}
    if args.action == "delete_folder":
        ex.execute(P.PoolDeleteFolder(args.folderId or ""))
        return {"ok": True}
    if args.action == "update_asset":
        ex.execute(P.PoolUpdateAsset(args.assetId or "", args.patch or {}))
        return {"ok": True, "assetId": args.assetId}
    if args.action == "relink_asset":
        ex.execute(P.PoolRelinkAsset(args.assetId or "", args.src or ""))
        return {"ok": True, "assetId": args.assetId}
    if args.action == "canonicalize_asset":
        ex.execute(P.PoolCanonicalizeAsset(args.assetId or "", args.canonicalId or ""))
        return {"ok": True}
    return {"ok": False, "error": f"unknown action: {args.action}"}


def exec_set_design_style(args: SetDesignStyleArgs, ctx: ToolContext) -> dict:
    if args.action == "set":
        ctx.executor.execute(P.SetDesignStyle(args.style))
    else:
        ctx.executor.execute(P.PatchDesignStyle(args.patch or {}))
    return {"ok": True}


def exec_set_full_state(args: SetFullStateArgs, ctx: ToolContext) -> dict:
    ctx.executor.execute(P.SetFullState(args.patch))
    return {"ok": True}


# ── A-3 边角工具 ──────────────────────────────────────────────────────────

class SetAspectRatioArgs(BaseModel):
    width: int = Field(..., description="画布宽（帧内像素）")
    height: int = Field(..., description="画布高")
    fit: str | None = Field(None, description="适配方式")


class ChangeCamArgs(BaseModel):
    action: Literal["set_groups", "add_decision"] = Field(..., description="操作类型")
    groups: list[dict] | None = Field(None, description="set_groups 的机位组列表")
    groupId: str | None = Field(None, description="add_decision 的目标组 id")
    fromFrame: int | None = Field(None, description="切机区间起始帧")
    toFrame: int | None = Field(None, description="切机区间结束帧")
    angleId: str | None = Field(None, description="切到的机位 id")


class ManageLinkGroupArgs(BaseModel):
    action: Literal["add", "set"] = Field(..., description="操作类型")
    group: dict | None = Field(None, description="add 的联动组 {itemIds, anchorItemId, mode}")
    groups: list[dict] | None = Field(None, description="set 的联动组列表")


def exec_set_aspect_ratio(args: SetAspectRatioArgs, ctx: ToolContext) -> dict:
    ctx.executor.execute(MA.SetCanvas(args.width, args.height, args.fit))
    return {"ok": True, "width": args.width, "height": args.height}


def exec_change_cam(args: ChangeCamArgs, ctx: ToolContext) -> dict:
    if args.action == "set_groups":
        groups = tuple(
            MulticamGroup(
                id=g.get("id", _new_id()),
                referenceAngleId=g.get("referenceAngleId", ""),
                masterAngleId=g.get("masterAngleId", ""),
                angles=tuple(MulticamAngle(id=a.get("id", _new_id()), itemId=a.get("itemId", ""),
                                           label=a.get("label", ""), offsetFrames=a.get("offsetFrames", 0),
                                           confidence=a.get("confidence", 1.0))
                             for a in g.get("angles", [])),
                syncMethod=g.get("syncMethod", "source-timecode"),
            )
            for g in (args.groups or [])
        )
        ctx.executor.execute(MA.SetMulticamGroups(groups))
        return {"ok": True, "count": len(groups)}
    if args.action == "add_decision":
        ctx.executor.execute(MA.AddMulticamDecision(args.groupId or "", args.fromFrame or 0,
                                                    args.toFrame or 0, args.angleId or ""))
        return {"ok": True}
    return {"ok": False, "error": f"unknown action: {args.action}"}


def exec_manage_link_group(args: ManageLinkGroupArgs, ctx: ToolContext) -> dict:
    if args.action == "add":
        g = args.group or {}
        grp = TimelineLinkGroup(id=g.get("id", _new_id()), itemIds=tuple(g.get("itemIds", [])),
                                anchorItemId=g.get("anchorItemId", ""), mode=g.get("mode", "linked"))
        ctx.executor.execute(MA.AddLinkGroup(grp))
        return {"ok": True, "groupId": grp.id}
    if args.action == "set":
        groups = tuple(
            TimelineLinkGroup(id=g.get("id", _new_id()), itemIds=tuple(g.get("itemIds", [])),
                              anchorItemId=g.get("anchorItemId", ""), mode=g.get("mode", "linked"))
            for g in (args.groups or [])
        )
        ctx.executor.execute(MA.SetLinkGroups(groups))
        return {"ok": True, "count": len(groups)}
    return {"ok": False, "error": f"unknown action: {args.action}"}


# ── 工具清单 ───────────────────────────────────────────────────────────────

TOOLS: list[Tool] = [
    Tool("read_timeline", "读取当前时间线（轨道、片段、转场、字幕、标记）", ReadTimelineArgs, exec_read_timeline),
    Tool("read_project", "读取项目概览（时间线列表、素材数）", ReadProjectArgs, exec_read_project),
    Tool("edit_track", "轨道管理（create/update/delete/toggle）", EditTrackArgs, exec_edit_track),
    Tool("add_clip", "在轨道添加片段", AddClipArgs, exec_add_clip),
    Tool("remove_clip", "删除片段", RemoveClipArgs, exec_remove_clip),
    Tool("clear_timeline", "清空时间线", ClearTimelineArgs, exec_clear_timeline),
    Tool("duplicate_clip", "复制片段", DuplicateClipArgs, exec_duplicate_clip),
    Tool("split_clip", "在绝对帧分割片段", SplitClipArgs, exec_split_clip),
    Tool("move_clip", "移动片段到轨道/帧", MoveClipArgs, exec_move_clip),
    Tool("set_clip_timing", "重定时（起始帧/时长/源入点）", SetClipTimingArgs, exec_set_clip_timing),
    Tool("update_clip_props", "更新片段可编辑字段", UpdateClipPropsArgs, exec_update_clip_props),
    Tool("set_clip_volume", "设置片段音量", SetClipVolumeArgs, exec_set_clip_volume),
    Tool("set_clip_fade", "设置淡入淡出（帧）", SetClipFadeArgs, exec_set_clip_fade),
    Tool("set_clip_transform", "设置片段变换（缩放/位移/旋转）", SetClipTransformArgs, exec_set_clip_transform),
    Tool("set_clip_filters", "设置片段滤镜（亮度/对比度/饱和度/模糊）", SetClipFiltersArgs, exec_set_clip_filters),
    Tool("set_clip_speed", "设置片段播放速率", SetClipSpeedArgs, exec_set_clip_speed),
    Tool("set_clip_zoom", "设置片段缩放动画", SetClipZoomArgs, exec_set_clip_zoom),
    Tool("set_clip_effects", "设置片段 WebGL 特效栈", SetClipEffectsArgs, exec_set_clip_effects),
    Tool("add_transition", "添加转场（作用于片段交接处）", AddTransitionArgs, exec_add_transition),
    Tool("edit_transition", "更新/删除转场", EditTransitionArgs, exec_edit_transition),
    Tool("edit_captions", "字幕管理（set/update/set_hidden）", EditCaptionsArgs, exec_edit_captions),
    Tool("set_keyframe", "添加/覆盖关键帧", SetKeyframeArgs, exec_set_keyframe),
    Tool("remove_keyframe", "删除关键帧", RemoveKeyframeArgs, exec_remove_keyframe),
    Tool("clear_keyframes", "清空关键帧", ClearKeyframesArgs, exec_clear_keyframes),
    Tool("manage_markers", "标记管理（add/update/remove）", ManageMarkersArgs, exec_manage_markers),
    Tool("select_clips", "选择片段（select/select_many/select_all）", SelectClipsArgs, exec_select_clips),
    Tool("manage_media_pool", "素材池管理（add_asset/create_folder/move_assets/remove_asset）", ManageMediaPoolArgs, exec_manage_media_pool),
    Tool("undo_last_change", "撤销最近一次修改", UndoArgs, exec_undo),
    Tool("redo_last_change", "重做最近一次撤销", RedoArgs, exec_redo),
    Tool("set_item_transcript", "设置片段的词级转写", SetItemTranscriptArgs, exec_set_item_transcript),
    Tool("read_transcript", "读取片段的转写词与删词状态", ReadTranscriptArgs, exec_read_transcript),
    Tool("clean_script", "清理脚本：移除填充词 + 压缩停顿", CleanScriptArgs, exec_clean_script),
    Tool("delete_text", "按词索引删除转写词", DeleteTextArgs, exec_delete_text),
    Tool("manage_transcript", "转写修正/说话人/翻译变体", ManageTranscriptArgs, exec_manage_transcript),
    Tool("slip_item", "平移片段源窗口（帧）", SlipItemArgs, exec_slip_item),
    Tool("set_background_fill", "设置片段背景填充", SetBackgroundFillArgs, exec_set_background_fill),
    Tool("replace_media", "替换片段媒体源", ReplaceMediaArgs, exec_replace_media),
    Tool("update_watermark", "更新文字水印", UpdateWatermarkArgs, exec_update_watermark),
    Tool("set_item_denoise", "设置片段 AI 降噪", SetItemDenoiseArgs, exec_set_item_denoise),
    Tool("set_reframe_keyframe", "设置 reframe 关键帧", SetReframeKeyframeArgs, exec_set_reframe_keyframe),
    Tool("manage_timelines", "多时间线管理（create/switch/duplicate/delete/rename/retarget/set_hidden）", ManageTimelinesArgs, exec_manage_timelines),
    Tool("edit_media_pool", "素材池进阶（rename_folder/delete_folder/update_asset/relink_asset/canonicalize_asset）", EditMediaPoolArgs, exec_edit_media_pool),
    Tool("set_design_style", "设置/补丁品牌设计风格", SetDesignStyleArgs, exec_set_design_style),
    Tool("set_full_state", "整体更新激活时间线状态", SetFullStateArgs, exec_set_full_state),
    Tool("set_aspect_ratio", "重定画布比例（长转短/横转竖）", SetAspectRatioArgs, exec_set_aspect_ratio),
    Tool("change_cam", "多机位管理（set_groups/add_decision）", ChangeCamArgs, exec_change_cam),
    Tool("manage_link_group", "联动组管理（add/set，A/V 同动锁）", ManageLinkGroupArgs, exec_manage_link_group),
]
