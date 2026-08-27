"""命令层：每个编辑操作是一条 Command，作用于不可变状态并产出新状态。

对照 OpenChatCut `src/editor/reducerActions.ts` 的 Action 联合类型——文件顶部那条
注释「command actions (these map 1:1 to the future agent tools)」正是本层与工具层的
关系：UI 和 LLM 都只能通过 Command 改工程，因此每一步都可校验、可撤销。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace

from .model import Clip, Timeline


class Command(ABC):
    @abstractmethod
    def apply(self, state: Timeline) -> Timeline:
        """返回应用后的新状态，不原地修改旧状态。"""


@dataclass(frozen=True)
class AddClip(Command):
    clip_id: str
    label: str
    kind: str
    track_id: str
    start: float
    duration: float

    def apply(self, state: Timeline) -> Timeline:
        clip = Clip(id=self.clip_id, label=self.label, kind=self.kind,
                    start=self.start, duration=self.duration)
        tracks = tuple(
            replace(t, clips=t.clips + (clip,)) if t.id == self.track_id else t
            for t in state.tracks
        )
        return replace(state, tracks=tracks)


def _map_clip(state: Timeline, clip_id: str, fn) -> Timeline:
    tracks = tuple(
        replace(t, clips=tuple(fn(c) if c.id == clip_id else c for c in t.clips))
        for t in state.tracks
    )
    return replace(state, tracks=tracks)


@dataclass(frozen=True)
class SetClipDuration(Command):
    clip_id: str
    duration: float

    def apply(self, state: Timeline) -> Timeline:
        return _map_clip(state, self.clip_id,
                         lambda c: replace(c, duration=self.duration))


@dataclass(frozen=True)
class RemoveClip(Command):
    clip_id: str

    def apply(self, state: Timeline) -> Timeline:
        tracks = tuple(
            replace(t, clips=tuple(c for c in t.clips if c.id != self.clip_id))
            for t in state.tracks
        )
        return replace(state, tracks=tracks)


class Executor:
    """执行命令 + 撤销/重做。

    MVP 用「快照撤销」：每次 execute 把当前完整状态压入撤销栈，undo 弹出即可回退。
    OpenChatCut 用细粒度逆命令（更省内存、可精确 diff），这里是刻意简化，详见精读文档。
    """

    def __init__(self, initial: Timeline):
        self._state = initial
        self._undo: list[Timeline] = []
        self._redo: list[Timeline] = []

    @property
    def state(self) -> Timeline:
        return self._state

    def execute(self, cmd: Command) -> Timeline:
        self._undo.append(self._state)
        self._state = cmd.apply(self._state)
        self._redo.clear()
        return self._state

    def undo(self) -> Timeline | None:
        if not self._undo:
            return None
        self._redo.append(self._state)
        self._state = self._undo.pop()
        return self._state

    def redo(self) -> Timeline | None:
        if not self._redo:
            return None
        self._undo.append(self._state)
        self._state = self._redo.pop()
        return self._state
