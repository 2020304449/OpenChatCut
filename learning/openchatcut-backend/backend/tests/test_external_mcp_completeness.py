"""external MCP 完整度测试：registry 持久化 + 连接管理。"""
from fastapi.testclient import TestClient

from app.main import app
from app.mcp.registry import Registry


def test_registry_persist_and_load(tmp_path):
    """register 后新 Registry 同 db load 能恢复 editor。"""
    db = str(tmp_path / "ext.sqlite3")
    reg = Registry(db)
    reg.register("default", "editor-1", "rev-0", tools=[{"name": "add_clip"}])
    cap = reg.get("default").capability

    reg2 = Registry(db)   # 模拟重启
    reg2.load()
    loaded = reg2.get("default")
    assert loaded is not None
    assert loaded.editorInstanceId == "editor-1"
    assert loaded.capability == cap          # capability 也持久化
    assert loaded.toolNames == ["add_clip"]


def test_registry_list_and_unregister():
    reg = Registry()
    reg.register("p1", "e1", "r0")
    reg.register("p2", "e2", "r0")
    assert len(reg.list()) == 2
    reg.unregister("p1")
    assert len(reg.list()) == 1
    assert reg.get("p1") is None


def test_connections_and_disconnect():
    """connections 列出注册、disconnect 后消失。"""
    client = TestClient(app)
    pid = "test-proj"   # 独立 projectId，避免与别的测试冲突
    r = client.post("/api/external-agent/register", json={
        "projectId": pid, "editorId": "e1", "baseRevision": "r0",
        "tools": [{"name": "add_clip"}],
    })
    assert r.status_code == 200

    r = client.get("/api/external-agent/connections")
    assert r.status_code == 200
    pids = [c["projectId"] for c in r.json()["connections"]]
    assert pid in pids

    r = client.post("/api/external-agent/disconnect", json={"projectId": pid})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get("/api/external-agent/connections")
    pids = [c["projectId"] for c in r.json()["connections"]]
    assert pid not in pids
