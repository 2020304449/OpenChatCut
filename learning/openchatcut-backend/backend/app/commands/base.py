"""命令层基础：Command 协议 + Executor（快照撤销/重做）。

撤销单位 = 命令节点（一条命令一个撤销节点，对齐 OpenChatCut 的「编辑可追踪、
可撤销」契约）。MVP 用快照撤销（每条命令保存上个完整状态），后续可升级为逆命令。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.timeline import ProjectDoc


class Command(ABC):
    @abstractmethod
    def apply(self, state: ProjectDoc) -> ProjectDoc:
        """返回应用后的新工程状态，不原地修改旧状态。"""


class Executor:
    def __init__(self, initial: ProjectDoc):
        self._state = initial
        self._undo: list[ProjectDoc] = []
        self._redo: list[ProjectDoc] = []

    @property
    def state(self) -> ProjectDoc:
        return self._state

    def execute(self, cmd: Command) -> ProjectDoc:
        self._undo.append(self._state)
        self._state = cmd.apply(self._state)
        self._redo.clear()
        return self._state

    def undo(self) -> ProjectDoc | None:
        if not self._undo:
            return None
        self._redo.append(self._state)
        self._state = self._undo.pop()
        return self._state

    def redo(self) -> ProjectDoc | None:
        if not self._redo:
            return None
        self._undo.append(self._state)
        self._state = self._redo.pop()
        return self._state
