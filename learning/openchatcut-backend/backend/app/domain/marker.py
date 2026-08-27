"""标记模型：时间线标注 / TODO 锚点（对齐 src/editor/markerTypes.ts 核心字段）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Marker:
    id: str
    name: str
    frame: int | None = None        # 点标记
    startFrame: int | None = None   # 范围标记
    endFrame: int | None = None
    color: str | None = None
