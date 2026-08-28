"""本地 ffmpeg / ffprobe 定位：环境变量 → 内置 .tools/ → PATH。

服务器用 apt 装 ffmpeg 走 PATH；本地无系统安装时回退到 backend/.tools/ffmpeg-*/bin/。
"""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _bundled(bin_name: str) -> str | None:
    tools = BACKEND_ROOT / ".tools"
    if not tools.is_dir():
        return None
    for d in sorted(tools.iterdir()):
        if d.is_dir():
            exe = d / "bin" / bin_name
            if exe.is_file():
                return str(exe)
    return None


def ffmpeg_bin() -> str:
    return os.environ.get("OPENCHATCUT_FFMPEG") or os.environ.get("FFMPEG_PATH") or _bundled("ffmpeg.exe") or "ffmpeg"


def ffprobe_bin() -> str:
    return os.environ.get("OPENCHATCUT_FFPROBE") or os.environ.get("FFPROBE_PATH") or _bundled("ffprobe.exe") or "ffprobe"
