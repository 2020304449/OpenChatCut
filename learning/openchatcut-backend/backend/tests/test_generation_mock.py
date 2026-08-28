"""C+D 生成类 mock 存根 + 服务桥接工具测试。"""
import pytest

from app.agent.mock_generation import MockJobStore
from app.agent.registry import build_registry
from app.agent.tools import ToolContext
from app.commands.base import Executor
from app.domain.timeline import default_project


@pytest.fixture(autouse=True)
def _reset_job_store():
    MockJobStore._instance = None
    yield
    MockJobStore._instance = None


def _ctx():
    return ToolContext(Executor(default_project()))


def _call(name, args, ctx=None):
    return build_registry().execute(name, args, ctx or _ctx())


def test_submit_image_sync_generates_assets():
    ctx = _ctx()
    r = _call("submit_image", {"prompt": "一只猫", "name": "猫图", "count": 2}, ctx)
    assert r["ok"] is True
    assert len(r["generated"]) == 2
    assert r["addedTo"] == "media-pool-and-proposed-timeline"
    assert len(ctx.executor.state.assets) == 2


def test_submit_voice_sync_adds_asset():
    ctx = _ctx()
    r = _call("submit_voice", {"text": "你好", "name": "配音"}, ctx)
    assert r["ok"] is True
    assert r["assetId"]
    assert any(a.id == r["assetId"] for a in ctx.executor.state.assets)


def test_submit_music_async_then_track_progress():
    ctx = _ctx()
    r = _call("submit_music", {"prompt": "欢快", "name": "bgm"}, ctx)
    assert r["ok"] is True
    job_id = r["jobId"]
    assert job_id.startswith("job_")
    # 异步：此刻尚未进 pool
    assert len(ctx.executor.state.assets) == 0

    r2 = _call("track_progress", {"action": "wait", "jobIds": job_id}, ctx)
    assert r2["ok"] is True
    assert r2["reports"][0]["status"] == "completed"
    assert len(r2["addedAssets"]) == 1
    assert len(ctx.executor.state.assets) == 1  # wait 后资产落 pool


def test_submit_sound_sonilo_async_vs_elevenlabs_sync():
    ctx = _ctx()
    r_sonilo = _call("submit_sound", {"provider": "sonilo", "name": "音效"}, ctx)
    assert "jobId" in r_sonilo

    r_el = _call("submit_sound", {"provider": "elevenlabs", "prompt": "爆炸", "name": "音效2"}, ctx)
    assert r_el["ok"] is True
    assert "assetId" in r_el


def test_rerun_generation_creates_new_job():
    r = _call("submit_video", {"model": "seedance2", "prompt": "海浪", "name": "视频"})
    job_id = r["jobId"]
    r2 = _call("rerun_generation", {"jobId": job_id})
    assert r2["ok"] is True
    assert r2["jobId"] != job_id


def test_idempotency_key_returns_same_asset():
    key = "k-123"
    r1 = _call("submit_image", {"prompt": "a", "name": "x", "idempotencyKey": key})
    r2 = _call("submit_image", {"prompt": "a", "name": "x", "idempotencyKey": key})
    assert r1["generated"][0]["assetId"] == r2["generated"][0]["assetId"]


def test_submit_render_job_then_track_export():
    ctx = _ctx()
    r = _call("submit_render_job", {"format": "video", "codec": "h264"}, ctx)
    assert r["ok"] is True
    render_id = r["renderId"]

    r2 = _call("track_export", {"action": "wait", "renderIds": render_id}, ctx)
    assert r2["ok"] is True
    assert r2["status"] == "completed"
    assert "downloadUrl" in r2


def test_transcribe_track_no_src_clips():
    ctx = _ctx()
    r = _call("transcribe_track", {"track": "A1"}, ctx)
    assert r["ok"] is True
    assert r["clips"] == 0
    assert r["results"] == []


def test_probe_media_missing_graceful():
    r = _call("probe_media", {"source": "/nonexistent.mp4"})
    assert r["ok"] is False
