"""转场模型（对齐 src/editor/transitionTypes.ts 核心字段）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionItem:
    id: str
    incomingItemId: str           # 转场作用于其起始端的相邻片段
    transType: str
    durationInFrames: int | None = None
