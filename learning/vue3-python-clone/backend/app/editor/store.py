"""内存工程仓库：单工程门面，工具层与 HTTP 层都通过它改状态。"""
from __future__ import annotations

from .commands import Executor
from .model import Timeline, default_timeline, timeline_to_dict


class ProjectStore:
    def __init__(self, initial: Timeline | None = None):
        self._executor = Executor(initial if initial is not None else default_timeline())

    @property
    def state(self) -> Timeline:
        return self._executor.state

    def apply(self, cmd) -> Timeline:
        return self._executor.execute(cmd)

    def undo(self) -> Timeline | None:
        return self._executor.undo()

    def redo(self) -> Timeline | None:
        return self._executor.redo()

    def to_dict(self) -> dict:
        return timeline_to_dict(self._executor.state)
