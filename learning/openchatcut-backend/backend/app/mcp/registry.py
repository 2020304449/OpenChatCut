"""browser 注册表（对齐 server/external-agent/broker-registry.ts）。

browser register → 返回 registrationCapability（43 位 base64url），后续 poll/result
用它作鉴权头。baseRevision 用于防漂移。
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field


@dataclass
class EditorRegistration:
    projectId: str
    editorInstanceId: str
    baseRevision: str
    capability: str                 # 43 位 base64url
    ownershipEpoch: int
    toolNames: list[str] = field(default_factory=list)


class Registry:
    def __init__(self) -> None:
        self._editors: dict[str, EditorRegistration] = {}
        self._epoch = 0

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
        return reg

    def get(self, project_id: str) -> EditorRegistration | None:
        return self._editors.get(project_id)

    def unregister(self, project_id: str) -> None:
        self._editors.pop(project_id, None)

    def verify(self, project_id: str, capability: str | None) -> bool:
        if not capability:
            return False
        reg = self._editors.get(project_id)
        return reg is not None and reg.capability == capability

    def update_revision(self, project_id: str, base_revision: str) -> None:
        reg = self._editors.get(project_id)
        if reg:
            reg.baseRevision = base_revision
