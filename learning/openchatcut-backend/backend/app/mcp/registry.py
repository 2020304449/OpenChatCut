"""browser 注册表（对齐 server/external-agent/broker-registry.ts）。

browser register → 返回 registrationCapability（43 位 base64url），后续 poll/result
用它作鉴权头。baseRevision 用于防漂移。
"""
from __future__ import annotations

import dataclasses
import json
import os
import secrets
from dataclasses import dataclass, field

from ..storage.sqlite_store import SqliteStore


@dataclass
class EditorRegistration:
    projectId: str
    editorInstanceId: str
    baseRevision: str
    capability: str                 # 43 位 base64url
    ownershipEpoch: int
    toolNames: list[str] = field(default_factory=list)


class Registry:
    def __init__(self, db_path: str | None = None) -> None:
        self._editors: dict[str, EditorRegistration] = {}
        self._epoch = 0
        self._db_path = db_path

    def register(
        self,
        project_id: str,
        editor_id: str,
        base_revision: str,
        tools: list[dict] | None = None,
    ) -> EditorRegistration:
        self._epoch += 1
        reg = EditorRegistration(
            projectId=project_id,
            editorInstanceId=editor_id,
            baseRevision=base_revision,
            capability=secrets.token_urlsafe(32),   # 32 bytes → 43 位 base64url
            ownershipEpoch=self._epoch,
            toolNames=[t.get("name", "") for t in (tools or [])],
        )
        self._editors[project_id] = reg
        self._persist()
        return reg

    def get(self, project_id: str) -> EditorRegistration | None:
        return self._editors.get(project_id)

    def unregister(self, project_id: str) -> None:
        self._editors.pop(project_id, None)
        self._persist()

    def verify(self, project_id: str, capability: str | None) -> bool:
        if not capability:
            return False
        reg = self._editors.get(project_id)
        return reg is not None and reg.capability == capability

    def update_revision(self, project_id: str, base_revision: str) -> None:
        reg = self._editors.get(project_id)
        if reg:
            reg.baseRevision = base_revision
            self._persist()

    def list(self) -> list[EditorRegistration]:
        return list(self._editors.values())

    def _persist(self) -> None:
        """把 registry 状态落盘（SQLite）。db_path 为 None 时不持久化。"""
        if not self._db_path:
            return
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        store = SqliteStore(self._db_path)
        try:
            store.put("registry:state", json.dumps({
                "epoch": self._epoch,
                "editors": {pid: dataclasses.asdict(reg) for pid, reg in self._editors.items()},
            }, ensure_ascii=False))
        finally:
            store.close()

    def load(self) -> None:
        """从 SQLite 恢复 registry 状态。"""
        if not self._db_path or not os.path.exists(self._db_path):
            return
        store = SqliteStore(self._db_path)
        try:
            raw = store.get("registry:state")
            if raw:
                data = json.loads(raw)
                self._epoch = data.get("epoch", 0)
                self._editors = {
                    pid: EditorRegistration(**rd)
                    for pid, rd in data.get("editors", {}).items()
                }
        finally:
            store.close()
