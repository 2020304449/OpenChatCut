"""MCP broker + registry 状态机测试。"""
import asyncio

from app.mcp.broker import Broker, EditorBinding
from app.mcp.registry import Registry


def test_broker_invoke_then_settle_applied():
    async def scenario():
        b = Broker()
        binding = EditorBinding(projectId="p1", editorInstanceId="e1", baseRevision="rev1")
        fut = b.invoke(binding, "add_clip", {"track": "V1"})

        call = await b.next_call("p1")
        assert call is not None
        assert call.name == "add_clip"
        assert call.arguments == {"track": "V1"}
        assert call.state == "in_flight"

        b.settle(call.id, "applied", {"ok": True, "assetId": "a1"})
        result = await fut
        assert result == {"ok": True, "assetId": "a1"}
    asyncio.run(scenario())


def test_broker_reject_outcome_raises():
    async def scenario():
        b = Broker()
        binding = EditorBinding(projectId="p1", editorInstanceId="e1", baseRevision="rev1")
        fut = b.invoke(binding, "submit_image", {"prompt": "x"})
        call = await b.next_call("p1")
        b.settle(call.id, "rejected", message="user declined")
        try:
            await fut
            assert False, "should have rejected"
        except Exception as exc:
            assert "rejected" in str(exc)
    asyncio.run(scenario())


def test_broker_long_poll_woken_by_invoke():
    async def scenario():
        b = Broker()
        binding = EditorBinding(projectId="p1", editorInstanceId="e1", baseRevision="rev1")
        # 先启动长轮询（空队列会挂起等待）
        next_task = asyncio.create_task(b.next_call("p1"))
        await asyncio.sleep(0.05)  # 让 next_call 进入等待状态
        fut = b.invoke(binding, "add_clip", {})
        # invoke 唤醒长轮询
        call = await asyncio.wait_for(next_task, timeout=1)
        assert call is not None
        assert call.name == "add_clip"
        b.settle(call.id, "applied", {"ok": True})
        await fut
    asyncio.run(scenario())


def test_registry_register_and_verify():
    r = Registry()
    reg = r.register("p1", "e1", "rev1", [{"name": "add_clip"}, {"name": "remove_clip"}])
    assert len(reg.capability) == 43
    assert reg.toolNames == ["add_clip", "remove_clip"]
    assert r.verify("p1", reg.capability) is True
    assert r.verify("p1", "wrong") is False
    assert r.verify("p2", reg.capability) is False
    assert r.verify("p1", None) is False

    r.update_revision("p1", "rev2")
    assert r.get("p1").baseRevision == "rev2"
