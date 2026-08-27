"""A-3 边角命令：轨道收紧、画布、多机位、联动组。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

from ..domain.multicam import MulticamAngleDecision, MulticamGroup, TimelineLinkGroup
from ..domain.timeline import ProjectDoc, Timeline
from .actions import _map_active
from .base import Command


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass(frozen=True)
class TrackTighten(Command):
    """同轨道 item 按 startFrame 排序后从 0 紧凑排列（去空隙）。"""
    track: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            track_items = sorted((i for i in tl.items if i.track == self.track),
                                 key=lambda i: i.startFrame)
            new_start: dict[str, int] = {}
            cursor = 0
            for i in track_items:
                new_start[i.id] = cursor
                cursor += i.durationInFrames
            items = tuple(
                replace(i, startFrame=new_start[i.id]) if i.id in new_start else i
                for i in tl.items
            )
            return replace(tl, items=items)
        return _map_active(doc, fn)


@dataclass(frozen=True)
class SetCanvas(Command):
    width: int
    height: int
    fit: str | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(doc, lambda tl: replace(tl, width=self.width, height=self.height, fit=self.fit))


@dataclass(frozen=True)
class SetMulticamGroups(Command):
    groups: tuple[MulticamGroup, ...]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(doc, lambda tl: replace(tl, multicamGroups=self.groups))


@dataclass(frozen=True)
class AddMulticamDecision(Command):
    group_id: str
    from_frame: int
    to_frame: int
    angle_id: str
    decision_id: str | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            decision = MulticamAngleDecision(id=self.decision_id or _new_id(),
                                             fromFrame=self.from_frame, toFrame=self.to_frame,
                                             angleId=self.angle_id)
            groups = tuple(
                replace(g, decisions=g.decisions + (decision,)) if g.id == self.group_id else g
                for g in tl.multicamGroups
            )
            return replace(tl, multicamGroups=groups)
        return _map_active(doc, fn)


@dataclass(frozen=True)
class SetLinkGroups(Command):
    groups: tuple[TimelineLinkGroup, ...]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(doc, lambda tl: replace(tl, linkGroups=self.groups))


@dataclass(frozen=True)
class AddLinkGroup(Command):
    group: TimelineLinkGroup

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(doc, lambda tl: replace(tl, linkGroups=tl.linkGroups + (self.group,)))
