"""项目持久化 HTTP 端点：browser 权威 state → SQLite 落盘 → 重启加载。

- GET  /api/project：读 load_project()，无数据返回 {exists:false}
- PUT  /api/project：body.state（完整 ProjectDoc dict）→ project_from_dict 校验 → save_project

走 persist.py 默认路径（OPENCHATCUT_DATA_DIR 或 data/），不持有连接，每次 open→close。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .domain.timeline import project_to_dict
from .persist import load_project, project_from_dict, save_project

router = APIRouter(prefix="/api/project")


class PutBody(BaseModel):
    state: dict


@router.get("")
def get_project():
    doc = load_project()
    if doc is None:
        return {"exists": False}
    return {"exists": True, "state": project_to_dict(doc)}


@router.put("")
def put_project(body: PutBody):
    try:
        doc = project_from_dict(body.state)
    except Exception as exc:
        raise HTTPException(400, f"invalid project state: {exc}")
    save_project(doc)
    return {"ok": True}
