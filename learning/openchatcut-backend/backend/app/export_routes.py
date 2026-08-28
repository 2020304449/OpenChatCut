"""导出 HTTP 端点：接收 browser 权威 state → FFmpeg 渲染 → 下载文件。

前端「导出」按钮把 useEditor 的 ProjectDoc（dict）POST 过来，后端还原成 Timeline
后渲染。前端的 /media/xxx 相对 src 映射到 frontend/public/media 的真实文件路径。
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .domain.timeline import active_timeline
from .persist import data_dir, project_from_dict
from .services.export import render_timeline

router = APIRouter(prefix="/api/export")

# 学习仓库结构：backend/ 与 frontend/ 平级，媒体在 frontend/public/。
FRONTEND_PUBLIC = Path(__file__).resolve().parents[2] / "frontend" / "public"


class ExportBody(BaseModel):
    state: dict
    name: str = "export"
    format: str = "video"
    codec: str = "h264"
    fps: int | None = None


def _resolve_src(src: str | None) -> str | None:
    if not src:
        return None
    if src.startswith("/media/"):
        # /media/xxx → frontend/public/media/xxx（去掉开头的 /，保留 media/ 目录）
        return str(FRONTEND_PUBLIC / src[1:])
    return src


@router.post("")
def export(body: ExportBody):
    doc = project_from_dict(body.state)
    tl = active_timeline(doc)

    # browser 相对 src → 真实文件路径
    items = tuple(dataclasses.replace(i, src=_resolve_src(i.src)) for i in tl.items)
    tl = dataclasses.replace(tl, items=items)

    safe_name = "".join(c for c in body.name if c.isalnum() or c in "-_") or "export"
    ext = "mp4" if body.codec == "h264" else "webm" if body.codec == "vp8" else "mp4"
    out_dir = Path(data_dir()) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe_name}.{ext}"

    r = render_timeline(tl, str(out_path), format=body.format, codec=body.codec, fps=body.fps)
    if not r["ok"]:
        return JSONResponse(status_code=400, content={"ok": False, "error": r["error"]})

    media_type = "video/mp4" if ext == "mp4" else "video/webm"
    return FileResponse(str(out_path), media_type=media_type, filename=f"{safe_name}.{ext}")
