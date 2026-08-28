"""项目持久化端点测试：GET/PUT /api/project round-trip。"""
from fastapi.testclient import TestClient

from app.commands import actions as A
from app.commands.base import Executor
from app.domain.captions import CaptionCue, CaptionsData
from app.domain.item import TimelineItem
from app.domain.timeline import default_project, project_to_dict
from app.main import app

client = TestClient(app)


def _make_doc():
    ex = Executor(default_project())
    ex.execute(A.AddItem(TimelineItem(id="i1", track="V1", startFrame=0,
                                      durationInFrames=90, name="A", kind="video", volume=0.5)))
    ex.execute(A.SetCaptions(CaptionsData(items=(CaptionCue(0, 90, "你好"),))))
    return ex.state


def test_get_project_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCHATCUT_DATA_DIR", str(tmp_path))
    r = client.get("/api/project")
    assert r.status_code == 200
    assert r.json() == {"exists": False}


def test_put_then_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCHATCUT_DATA_DIR", str(tmp_path))
    state = project_to_dict(_make_doc())

    put = client.put("/api/project", json={"state": state})
    assert put.status_code == 200
    assert put.json() == {"ok": True}

    got = client.get("/api/project").json()
    assert got["exists"] is True
    # round-trip 稳定：PUT 的规范化形式 == GET 返回
    assert got["state"] == state


def test_restart_recovers(tmp_path, monkeypatch):
    """PUT 后重新 GET（每次 load 都重新 open SQLite）仍能读到。"""
    monkeypatch.setenv("OPENCHATCUT_DATA_DIR", str(tmp_path))
    state = project_to_dict(_make_doc())
    client.put("/api/project", json={"state": state})

    # 模拟重启：新连接读同一 DB
    got = client.get("/api/project").json()
    assert got["exists"] is True
    assert got["state"]["activeTimelineId"] == state["activeTimelineId"]
    assert got["state"]["timelines"][0]["items"][0]["name"] == "A"
