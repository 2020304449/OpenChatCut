"""生成/导出类工具的 mock 存根共享层。

对齐原版「schema + 幂等包装 + executor」三层的中间两层：
- MockJobStore：进程内 job 注册表（对齐 jobRegistryStore 简化版）+ 幂等缓存
- mock_asset：生成假资产（对齐「生成落点进媒体池」语义）
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..domain.media import MediaAsset

_KIND_EXT = {
    "image": "png",
    "video": "mp4",
    "audio": "mp3",
    "voice": "mp3",
    "sound": "wav",
    "music": "mp3",
}

_KIND_DIMS = {
    "image": (1024, 1024),
    "video": (1920, 1080),
    "motion-graphic": (1920, 1080),
}


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def mock_asset(
    kind: str,
    name: str,
    duration_in_frames: int | None = None,
    width: int | None = None,
    height: int | None = None,
    folder_id: str | None = None,
) -> MediaAsset:
    """生成一个假资产（src 用 /media/uploads 假路径）。"""
    ext = _KIND_EXT.get(kind)
    src = f"/media/uploads/{_new_id()}.{ext}" if ext else ""
    default_w, default_h = _KIND_DIMS.get(kind, (None, None))
    return MediaAsset(
        id="a" + _new_id(),
        name=name,
        kind=kind,
        src=src,
        durationInFrames=duration_in_frames,
        width=width if width is not None else default_w,
        height=height if height is not None else default_h,
        folderId=folder_id,
    )


@dataclass
class MockJob:
    job_id: str
    kind: str
    status: str = "pending"          # pending | completed
    result: dict = field(default_factory=dict)
    args: dict = field(default_factory=dict)


class MockJobStore:
    """进程内 mock job 注册表 + 幂等缓存。"""

    _instance: "MockJobStore | None" = None

    def __init__(self) -> None:
        self._jobs: dict[str, MockJob] = {}
        self._idempotency: dict[str, str] = {}

    @classmethod
    def instance(cls) -> "MockJobStore":
        if cls._instance is None:
            cls._instance = MockJobStore()
        return cls._instance

    def register(self, kind: str, args: dict, idempotency_key: str | None = None) -> MockJob:
        if idempotency_key and idempotency_key in self._idempotency:
            return self._jobs[self._idempotency[idempotency_key]]
        job = MockJob(job_id="job_" + _new_id(), kind=kind, args=args)
        self._jobs[job.job_id] = job
        if idempotency_key:
            self._idempotency[idempotency_key] = job.job_id
        return job

    def get(self, job_id: str) -> MockJob | None:
        return self._jobs.get(job_id)

    def resolve(self, ref: str) -> MockJob | None:
        """精确 id 或唯一前缀解析。"""
        if ref in self._jobs:
            return self._jobs[ref]
        matches = [j for k, j in self._jobs.items() if k.startswith(ref)]
        return matches[0] if len(matches) == 1 else None

    def complete(self, job_id: str, result: dict) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = "completed"
            job.result = result
