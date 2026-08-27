"""多机位与联动组数据模型（对齐 src/editor/multicamTypes.ts）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimelineLinkGroup:
    id: str
    itemIds: tuple[str, ...]
    anchorItemId: str
    mode: str            # 'linked' | 'sync-lock'


@dataclass(frozen=True)
class MulticamAngle:
    id: str
    itemId: str
    label: str
    offsetFrames: int = 0
    confidence: float = 1.0


@dataclass(frozen=True)
class MulticamAngleDecision:
    id: str
    fromFrame: int
    toFrame: int
    angleId: str


@dataclass(frozen=True)
class MulticamGroup:
    id: str
    referenceAngleId: str
    masterAngleId: str
    angles: tuple[MulticamAngle, ...] = ()
    syncMethod: str = "source-timecode"
    decisions: tuple[MulticamAngleDecision, ...] = ()
