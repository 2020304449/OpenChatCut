"""轨道模型：TrackKind / TrackFlags（对齐 src/editor/trackTypes.ts）。"""
from __future__ import annotations

from dataclasses import dataclass

TrackKind = str          # 'video' | 'audio' | 'caption'
TrackId = str
TrackRole = str          # 'anchor' | 'follower'

# 默认轨道顺序（对齐 TRACK_ORDER）
TRACK_ORDER: tuple[TrackId, ...] = ("V2", "V1", "A1", "A2")


@dataclass(frozen=True)
class TrackFlags:
    kind: TrackKind | None = None
    name: str | None = None
    hidden: bool = False
    muted: bool = False
    locked: bool = False
    collapsed: bool = False
    role: TrackRole | None = None
