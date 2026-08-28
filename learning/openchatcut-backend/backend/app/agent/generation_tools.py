"""生成/导出类工具（对齐原版 deferred-tools.md 契约，mock 存根 + 真实服务桥接）。

- 生成类：mock 存根，同步返回假资产 / 异步返回 jobId
- 导出类：submit_export 接真实 FFmpeg，render_job/track_export 走 mock job store
- transcribe_track：接 faster-whisper；probe_media：接 ffprobe
"""
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

from ..commands import actions as A
from ..commands import transcript_actions as TA
from ..domain.timeline import active_timeline
from ..services import export as export_service
from ..services import probe as probe_service
from ..services.fcpxml import timeline_to_fcpxml
from ..services.transcription import transcribe_audio
from .mock_generation import MockJobStore, mock_asset
from .tools import Tool, ToolContext


def _store() -> MockJobStore:
    return MockJobStore.instance()


def _add_asset(ctx: ToolContext, asset) -> str:
    ctx.executor.execute(A.AddAsset(asset))
    return asset.id


def _export_path(name: str | None, ext: str) -> str:
    base = os.environ.get("OPENCHATCUT_DATA_DIR", "data")
    d = os.path.join(base, "exports")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{name or 'export'}.{ext}")


# ── 同步生成类 ─────────────────────────────────────────────────────────────

class SubmitImageArgs(BaseModel):
    prompt: str = Field(..., description="图片生成提示词")
    name: str = Field(..., description="资产名")
    model: str = "gpt-image-2"
    aspectRatio: str | None = None
    count: int = Field(1, ge=1, le=10)
    width: int | None = None
    height: int | None = None
    addToTimeline: bool = True
    idempotencyKey: str | None = None


def exec_submit_image(args: SubmitImageArgs, ctx: ToolContext) -> dict:
    store = _store()
    job = store.register("image", args.model_dump(), args.idempotencyKey)
    if job.status == "completed":
        return job.result
    generated = []
    for _ in range(args.count):
        a = mock_asset("image", args.name, width=args.width, height=args.height)
        _add_asset(ctx, a)
        generated.append({"assetId": a.id, "name": a.name, "src": a.src,
                          "width": a.width, "height": a.height})
    result = {"ok": True, "model": args.model, "generated": generated,
              "addedTo": "media-pool-and-proposed-timeline" if args.addToTimeline else "media-pool"}
    store.complete(job.job_id, result)
    return result


class SubmitVoiceArgs(BaseModel):
    provider: str = Field("elevenlabs", description="TTS provider")
    text: str = Field(..., description="要合成的文本")
    name: str = "配音"
    voiceId: str | None = None
    idempotencyKey: str | None = None


def exec_submit_voice(args: SubmitVoiceArgs, ctx: ToolContext) -> dict:
    store = _store()
    job = store.register("voice", args.model_dump(), args.idempotencyKey)
    if job.status == "completed":
        return job.result
    a = mock_asset("voice", args.name)
    _add_asset(ctx, a)
    result = {"ok": True, "provider": args.provider, "voiceId": args.voiceId or "",
              "assetId": a.id, "name": a.name, "src": a.src, "addedTo": "media-pool"}
    store.complete(job.job_id, result)
    return result


class SubmitSoundArgs(BaseModel):
    provider: Literal["elevenlabs", "sonilo"] = "elevenlabs"
    prompt: str | None = Field(None, description="音效描述（elevenlabs 用）")
    durationSeconds: float = Field(2.0, ge=0.5, le=30)
    name: str = "音效"
    sourceAssetId: str | None = Field(None, description="sonilo 用：源视频资产")
    projectId: str | None = Field(None, description="durable 工具项目 id（单体缺省 default）")
    idempotencyKey: str | None = None


def exec_submit_sound(args: SubmitSoundArgs, ctx: ToolContext) -> dict:
    store = _store()
    job = store.register("sound", args.model_dump(), args.idempotencyKey)
    if job.status == "completed":
        return job.result
    if args.provider == "sonilo":
        result = {"ok": True, "jobId": job.job_id,
                  "next": f"Call track_progress ... jobIds={job.job_id}"}
        return result
    a = mock_asset("sound", args.name,
                   duration_in_frames=int(round(args.durationSeconds * 30)))
    _add_asset(ctx, a)
    result = {"ok": True, "assetId": a.id, "name": a.name, "src": a.src,
              "durationInFrames": a.durationInFrames, "addedTo": "media-pool"}
    store.complete(job.job_id, result)
    return result


# ── 异步生成类 ─────────────────────────────────────────────────────────────

class SubmitMusicArgs(BaseModel):
    prompt: str = Field(..., description="音乐描述")
    provider: str = "mureka"
    mode: str | None = None
    name: str = "音乐"
    projectId: str | None = Field(None, description="durable 工具项目 id（单体缺省 default）")
    idempotencyKey: str | None = None


def exec_submit_music(args: SubmitMusicArgs, ctx: ToolContext) -> dict:
    store = _store()
    job = store.register("music", args.model_dump(), args.idempotencyKey)
    if job.status == "completed":
        return job.result
    return {"ok": True, "jobId": job.job_id,
            "next": f"Call track_progress ... jobIds={job.job_id}"}


class SubmitVideoArgs(BaseModel):
    model: str = Field("seedance2", description="视频生成模型")
    prompt: str = Field(..., description="视频描述")
    name: str = "生成视频"
    durationSeconds: float = 5.0
    resolution: str | None = None
    projectId: str | None = Field(None, description="durable 工具项目 id（单体缺省 default）")
    idempotencyKey: str | None = None


def exec_submit_video(args: SubmitVideoArgs, ctx: ToolContext) -> dict:
    store = _store()
    job = store.register("video", args.model_dump(), args.idempotencyKey)
    if job.status == "completed":
        return job.result
    return {"ok": True, "model": args.model, "jobId": job.job_id,
            "next": f"Call track_progress ... jobIds={job.job_id}"}


class TrackProgressArgs(BaseModel):
    action: Literal["status", "wait", "resume"] = "status"
    target: Literal["generation", "transcription", "upload", "visual-analysis"] = "generation"
    jobIds: str = Field(..., description="逗号分隔的 job id 或前缀")
    timeoutSeconds: int = Field(90, ge=0, le=3600)


def exec_track_progress(args: TrackProgressArgs, ctx: ToolContext) -> dict:
    store = _store()
    reports = []
    added_assets = []
    for ref in [r.strip() for r in args.jobIds.split(",") if r.strip()]:
        job = store.resolve(ref)
        if job is None:
            reports.append({"jobId": ref, "status": "unknown"})
            continue
        # mock：wait 时把 pending job 置完成，生成假资产
        if args.action == "wait" and job.status == "pending":
            asset_kind = job.kind if job.kind in ("music", "video", "sound", "voice", "image") else "video"
            a = mock_asset(asset_kind, job.args.get("name", job.kind))
            _add_asset(ctx, a)
            store.complete(job.job_id, {"assetId": a.id, "name": a.name, "src": a.src})
            added_assets.append({"assetId": a.id, "name": a.name, "src": a.src, "kind": asset_kind})
        job = store.get(job.job_id)  # 刷新
        reports.append({"jobId": job.job_id, "status": job.status, **job.result})
    result = {"ok": True, "target": args.target, "action": args.action, "reports": reports}
    if added_assets:
        result["addedAssets"] = added_assets
        result["addedTo"] = "media-pool"
    return result


class RerunGenerationArgs(BaseModel):
    jobId: str = Field(..., description="要重跑的 job id")


def exec_rerun_generation(args: RerunGenerationArgs, ctx: ToolContext) -> dict:
    store = _store()
    job = store.resolve(args.jobId)
    if job is None:
        return {"ok": False, "error": f"no tracked job: {args.jobId}",
                "code": "not_found"}
    new_job = store.register(job.kind, job.args)
    return {"ok": True, "rerunOf": job.job_id, "jobId": new_job.job_id,
            "next": f"Call track_progress ... jobIds={new_job.job_id}"}


# ── 动效类 ─────────────────────────────────────────────────────────────────

class SubmitMotionGraphicArgs(BaseModel):
    prompt: str | None = Field(None, description="动效描述")
    name: str = Field(..., description="资产名")
    durationSeconds: float = 3.0
    width: int = 1920
    height: int = 1080


def exec_submit_motion_graphic(args: SubmitMotionGraphicArgs, ctx: ToolContext) -> dict:
    a = mock_asset("motion-graphic", args.name,
                   duration_in_frames=int(round(args.durationSeconds * 30)),
                   width=args.width, height=args.height)
    _add_asset(ctx, a)
    return {"ok": True, "status": "succeeded", "jobId": f"mg_{a.id}", "assetId": a.id,
            "name": a.name, "kind": a.kind, "width": a.width, "height": a.height,
            "durationInFrames": a.durationInFrames}


class CreateMotionGraphicFromCodeArgs(BaseModel):
    code: str = Field(..., description="完整 React/JSX 代码")
    name: str = Field(..., description="资产名")
    width: int = 1920
    height: int = 1080
    durationInFrames: int | None = None
    durationInSeconds: float | None = None


def exec_create_motion_graphic_from_code(args: CreateMotionGraphicFromCodeArgs, ctx: ToolContext) -> dict:
    dur = args.durationInFrames or int(round((args.durationInSeconds or 3.0) * 30))
    a = mock_asset("motion-graphic", args.name, duration_in_frames=dur,
                   width=args.width, height=args.height)
    _add_asset(ctx, a)
    return {"ok": True, "assetId": a.id, "name": a.name, "kind": "motion-graphic",
            "width": a.width, "height": a.height, "durationInFrames": dur,
            "note": "mock：未做沙箱编译校验"}


class SubmitShaderArgs(BaseModel):
    type: Literal["effect", "transition"] = Field(..., description="shader 类型")
    prompt: str = Field(..., description="自然语言 shader 描述")
    name: str = "shader"


def exec_submit_shader(args: SubmitShaderArgs, ctx: ToolContext) -> dict:
    rid = "fx_" + args.name if args.type == "effect" else "tr_" + args.name
    if args.type == "effect":
        return {"ok": True, "effectId": rid, "name": args.name, "properties": []}
    a = mock_asset("motion-graphic", args.name)
    _add_asset(ctx, a)
    return {"ok": True, "transitionId": rid, "assetId": a.id, "name": args.name,
            "properties": []}


# ── 导出类 ─────────────────────────────────────────────────────────────────

class SubmitExportArgs(BaseModel):
    format: Literal["video", "audio", "subtitles", "xml"] = Field(..., description="导出格式")
    codec: str = "h264"
    subtitleFormat: str = "srt"
    name: str | None = None
    fps: int | None = None
    resolution: str | None = None
    timelineId: str | None = None
    startFrame: int | None = None
    endFrameExclusive: int | None = None


def exec_submit_export(args: SubmitExportArgs, ctx: ToolContext) -> dict:
    tl = active_timeline(ctx.executor.state)
    fps = args.fps or tl.fps or 30
    if args.format == "subtitles":
        if not tl.captions:
            return {"ok": False, "error": "no captions to export"}
        out = _export_path(args.name, args.subtitleFormat)
        return export_service.export_subtitles(tl.captions, fps, out)
    if args.format == "xml":
        out = _export_path(args.name, "fcpxml")
        try:
            with open(out, "w", encoding="utf-8") as f:
                f.write(timeline_to_fcpxml(tl))
            return {"ok": True, "path": out}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
    if args.format == "audio":
        ext = "mp3" if args.codec == "mp3" else "wav"
    else:
        ext = "mp4" if args.codec == "h264" else "webm" if args.codec == "vp8" else "mp4"
    out = _export_path(args.name, ext)
    return export_service.render_timeline(tl, out, format=args.format, codec=args.codec,
                                          fps=fps, start_frame=args.startFrame or 0,
                                          end_frame_exclusive=args.endFrameExclusive)


class SubmitRenderJobArgs(BaseModel):
    format: Literal["video", "audio"] = "video"
    codec: str = "h264"
    resolution: str | None = None
    fps: int | None = None
    name: str | None = None
    saveToMediaPool: bool = False


def exec_submit_render_job(args: SubmitRenderJobArgs, ctx: ToolContext) -> dict:
    store = _store()
    job = store.register("render", args.model_dump())
    return {"ok": True, "renderId": job.job_id, "format": args.format,
            "mediaPoolStatus": "pending" if args.saveToMediaPool else None,
            "next": f"Call track_export ... action=wait, renderIds={job.job_id}"}


class TrackExportArgs(BaseModel):
    action: Literal["status", "wait"] = "status"
    renderIds: str | None = None
    latest: bool = False
    timeoutSeconds: int = Field(20, ge=0, le=3600)


def exec_track_export(args: TrackExportArgs, ctx: ToolContext) -> dict:
    store = _store()
    refs = [r.strip() for r in (args.renderIds or "").split(",") if r.strip()]
    if args.latest or not refs:
        # 找最近的 render job
        latest = None
        for job in store._jobs.values():
            if job.kind == "render":
                latest = job
        refs = [latest.job_id] if latest else []
    if not refs:
        return {"ok": False, "error": "no render job"}
    out = []
    for ref in refs:
        job = store.resolve(ref)
        if job is None:
            out.append({"renderId": ref, "status": "unknown"})
            continue
        if args.action == "wait" and job.status == "pending":
            name = job.args.get("name") or "render"
            ext = "mp4" if job.args.get("codec") == "h264" else "webm"
            # mock：置完成，给假 downloadUrl
            store.complete(job.job_id, {"downloadUrl": f"/media/uploads/{job.job_id}.{ext}",
                                        "name": name, "codec": job.args.get("codec")})
            job = store.get(job.job_id)
        out.append({"ok": True, "renderId": job.job_id, "status": job.status, **job.result})
    if len(out) == 1:
        return out[0]
    return {"ok": True, "count": len(out), "jobs": out}


class VerifyExportArgs(BaseModel):
    renderId: str | None = None
    src: str | None = None


def exec_verify_export(args: VerifyExportArgs, ctx: ToolContext) -> dict:
    src = args.src or (args.renderId or "")
    return {"ok": True, "src": src, "report": {"issues": []}, "cutCount": 0,
            "evidenceSamples": [], "note": "mock：未做真实 QA 分析"}


class ExportMotionGraphicProresArgs(BaseModel):
    itemId: str | None = None
    itemIds: list[str] | None = None
    assetId: str | None = None
    assetIds: list[str] | None = None
    name: str | None = None


def exec_export_motion_graphic_prores(args: ExportMotionGraphicProresArgs, ctx: ToolContext) -> dict:
    ids = args.itemIds or ([args.itemId] if args.itemId else [])
    names = [f"{i}.mov" for i in (ids or ["motion-graphic"])]
    return {"ok": True, "format": "prores4444_mov", "transparent": True,
            "exported": names, "renders": [],
            "note": "mock：未做真实 ProRes 渲染"}


class ConvertMotionGraphicToVideoArgs(BaseModel):
    itemId: str | None = None
    assetId: str | None = None
    replace: bool = False
    opaque: bool = False


def exec_convert_motion_graphic_to_video(args: ConvertMotionGraphicToVideoArgs, ctx: ToolContext) -> dict:
    a = mock_asset("video", "baked-motion-graphic")
    _add_asset(ctx, a)
    codec = "h264" if args.opaque else "vp9-alpha-webm"
    return {"ok": True, "assetId": a.id, "src": a.src, "name": a.name,
            "replaced": args.replace, "transparent": not args.opaque, "codec": codec,
            "note": "mock：未做真实烘焙"}


class RegisterConvertedVideoArgs(BaseModel):
    mgAssetId: str = Field(..., description="MG 资产 id")
    renderId: str | None = None
    outputUrl: str | None = None
    name: str | None = None
    durationInFrames: int | None = None


def exec_register_converted_video(args: RegisterConvertedVideoArgs, ctx: ToolContext) -> dict:
    a = mock_asset("video", args.name or "converted", duration_in_frames=args.durationInFrames)
    _add_asset(ctx, a)
    return {"ok": True, "assetId": a.id, "videoAssetId": a.id, "mgAssetId": args.mgAssetId,
            "name": a.name, "durationInFrames": a.durationInFrames,
            "next": "video asset registered to media pool"}


class ExportJianyingDraftArgs(BaseModel):
    draftName: str = "剪映草稿"
    draftsDir: str | None = None


def exec_export_jianying_draft(args: ExportJianyingDraftArgs, ctx: ToolContext) -> dict:
    return {"ok": True, "draftName": args.draftName, "draftPath": args.draftsDir or "~/JianyingPro/Drafts",
            "addedVideos": [], "addedAudios": [], "captions": [], "warnings": [],
            "note": "mock：未调用 capcut-cli"}


# ── 服务桥接：转写 / 探测 ─────────────────────────────────────────────────

class TranscribeTrackArgs(BaseModel):
    track: str = "A1"
    provider: str = "local"


def exec_transcribe_track(args: TranscribeTrackArgs, ctx: ToolContext) -> dict:
    tl = active_timeline(ctx.executor.state)
    clips = [i for i in tl.items if i.track == args.track and i.kind in ("audio", "video") and i.src]
    results = []
    for it in clips:
        r = transcribe_audio(it.src)
        if r.get("ok"):
            words = tuple(r["words"])
            ctx.executor.execute(TA.SetItemTranscript(it.id, words, None))
            results.append({"itemId": it.id, "words": len(words), "text": " ".join(w.text for w in words)})
        elif r.get("code") == "no-audio":
            results.append({"itemId": it.id, "skipped": True, "skippedReason": "no-audio"})
        else:
            results.append({"itemId": it.id, "skipped": True, "skippedReason": r.get("error")})
    return {"ok": True, "track": args.track, "provider": args.provider,
            "clips": len(clips), "results": results}


class ProbeMediaArgs(BaseModel):
    source: str = Field(..., description="assetId/前缀、本地路径或 https URL")


def _resolve_src(source: str, ctx: ToolContext) -> str:
    for a in ctx.executor.state.assets:
        if a.id == source or a.id.startswith(source):
            return a.src
    return source


def exec_probe_media(args: ProbeMediaArgs, ctx: ToolContext) -> dict:
    src = _resolve_src(args.source, ctx)
    result = probe_service.probe_media(src)
    if not result.get("ok"):
        return result
    return {"ok": True, "source": args.source, **result}


# ── 工具清单 ───────────────────────────────────────────────────────────────

GENERATION_TOOLS: list[Tool] = [
    Tool("submit_image", "生成图片（mock）", SubmitImageArgs, exec_submit_image),
    Tool("submit_voice", "生成 TTS 配音（mock）", SubmitVoiceArgs, exec_submit_voice),
    Tool("submit_sound", "生成音效（mock）", SubmitSoundArgs, exec_submit_sound),
    Tool("submit_music", "提交音乐生成 job（mock）", SubmitMusicArgs, exec_submit_music),
    Tool("submit_video", "提交视频生成 job（mock）", SubmitVideoArgs, exec_submit_video),
    Tool("track_progress", "查询生成/转写 job 进度（mock）", TrackProgressArgs, exec_track_progress),
    Tool("rerun_generation", "重跑生成 job（mock）", RerunGenerationArgs, exec_rerun_generation),
    Tool("submit_motion_graphic", "生成动效资产（mock）", SubmitMotionGraphicArgs, exec_submit_motion_graphic),
    Tool("create_motion_graphic_from_code", "从代码注册动效（mock）", CreateMotionGraphicFromCodeArgs, exec_create_motion_graphic_from_code),
    Tool("submit_shader", "生成 WebGL shader（mock）", SubmitShaderArgs, exec_submit_shader),
    Tool("submit_export", "同步导出视频/音频/字幕/XML", SubmitExportArgs, exec_submit_export),
    Tool("submit_render_job", "提交异步渲染 job", SubmitRenderJobArgs, exec_submit_render_job),
    Tool("track_export", "查询渲染 job 进度", TrackExportArgs, exec_track_export),
    Tool("verify_export", "导出 QA 检查（mock）", VerifyExportArgs, exec_verify_export),
    Tool("export_motion_graphic_prores", "导出 MG ProRes（mock）", ExportMotionGraphicProresArgs, exec_export_motion_graphic_prores),
    Tool("convert_motion_graphic_to_video", "烘焙 MG 为视频（mock）", ConvertMotionGraphicToVideoArgs, exec_convert_motion_graphic_to_video),
    Tool("register_converted_video", "注册转换产物为资产（mock）", RegisterConvertedVideoArgs, exec_register_converted_video),
    Tool("export_jianying_draft", "导出剪映草稿（mock）", ExportJianyingDraftArgs, exec_export_jianying_draft),
    Tool("transcribe_track", "转写轨道音频为词级字幕（faster-whisper）", TranscribeTrackArgs, exec_transcribe_track),
    Tool("probe_media", "媒体探测（ffprobe）", ProbeMediaArgs, exec_probe_media),
]
