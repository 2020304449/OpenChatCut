"""C+D SQLite KV 持久化测试。"""
import json
import os

import app.persist as P
from app.commands import actions as A
from app.commands.base import Executor
from app.domain.captions import CaptionCue, CaptionsData
from app.domain.item import TimelineItem
from app.domain.timeline import active_timeline, default_project, project_to_dict
from app.persist import load_project, save_project
from app.storage.sqlite_store import SqliteStore


def _make_doc():
    ex = Executor(default_project())
    ex.execute(A.AddItem(TimelineItem(id="i1", track="V1", startFrame=0,
                                      durationInFrames=90, name="A", kind="video", volume=0.5)))
    ex.execute(A.SetCaptions(CaptionsData(items=(CaptionCue(0, 90, "你好"),))))
    return ex.state


def test_sqlite_store_roundtrip(tmp_path):
    s = SqliteStore(str(tmp_path / "s.sqlite3"))
    s.put("k1", json.dumps({"a": 1}))
    assert json.loads(s.get("k1")) == {"a": 1}
    s.put("k1", json.dumps({"a": 2}))  # upsert
    assert json.loads(s.get("k1")) == {"a": 2}
    s.delete("k1")
    assert s.get("k1") is None
    s.close()


def test_save_load_roundtrip(tmp_path):
    db = str(tmp_path / "p.sqlite3")
    doc = _make_doc()
    save_project(doc, db)
    loaded = load_project(db)
    assert loaded is not None
    assert active_timeline(loaded).items[0].name == "A"
    assert active_timeline(loaded).items[0].volume == 0.5
    assert active_timeline(loaded).captions.items[0].text == "你好"


def test_load_missing_db_returns_none(tmp_path):
    assert load_project(str(tmp_path / "nonexistent.sqlite3")) is None


def test_migrate_from_legacy_json(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    legacy = data_dir / "project.json"
    legacy.write_text(
        json.dumps(project_to_dict(_make_doc()), ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setenv("OPENCHATCUT_DATA_DIR", str(data_dir))

    loaded = P.load_project()
    assert loaded is not None
    assert active_timeline(loaded).items[0].name == "A"

    db_path = str(data_dir / "project-store.sqlite3")
    assert os.path.exists(db_path)
    s = SqliteStore(db_path)
    assert s.has_migration_receipt()
    assert s.get(P.PROJECT_KEY) is not None
    s.close()


def test_restart_recovers(tmp_path):
    db = str(tmp_path / "p.sqlite3")
    save_project(_make_doc(), db)
    loaded = load_project(db)  # 重新 open，模拟重启
    assert loaded is not None
    assert active_timeline(loaded).items[0].name == "A"
