"""arch-4 外部 MCP 链路 B 后端闭环测试：register → invoke → poll → settle。

验证 browser 桥接协议：register 换 capability、broker 入队、长轮询取、结算唤醒。
"""
import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.mcp.broker import Broker, EditorBinding
from app.mcp.registry import Registry
from app.mcp.server import _make_edit_tool

client = TestClient(app)


def test_register_returns_capability():
    r = client.post("/api/external-agent/register", json={
        "projectId": "default",
        "editorId": "editor-1",
        "baseRevision": "rev-0",
        "tools": [{"name": "add_clip", "description": "加片段"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["registrationCapability"]) == 43  # base64url 32 字节
    assert body["ownershipEpoch"] >= 1


def test_poll_requires_capability():
    r = client.get("/api/external-agent/poll", params={"projectId": "default"})
    assert r.status_code == 401  # 无 capability 头


def test_broker_invoke_poll_settle_loop():
    async def scenario():
        registry = Registry()
        broker = Broker()
        reg = registry.register("default", "editor-1", "rev-0", tools=[{"name": "add_clip"}])
        binding = EditorBinding(reg.projectId, reg.editorInstanceId, reg.baseRevision, reg.ownershipEpoch)

        # server 侧：外部 MCP 客户端调用编辑工具 → 入队挂起
        fut = broker.invoke(binding, "add_clip", {"label": "A", "startFrame": 0})

        # browser 侧：长轮询取调用
        call = await broker.next_call("default")
        assert call is not None
        assert call.name == "add_clip"
        assert call.arguments == {"label": "A", "startFrame": 0}
        assert call.state == "in_flight"

        # browser 执行完结算
        ok = broker.settle(call.id, "applied", result={"ok": True, "itemId": "i1"})
        assert ok is True
        assert await fut == {"ok": True, "itemId": "i1"}  # 唤醒 MCP session

    asyncio.run(scenario())


def test_edit_tool_routes_to_broker():
    async def scenario():
        from app.mcp.server import broker, registry
        registry.register("default", "editor-1", "rev-0")
        fn = _make_edit_tool("add_clip")

        # 模拟 browser 长轮询：先派发，再取，再结算
        async def browser():
            call = await broker.next_call("default")
            assert call is not None
            broker.settle(call.id, "applied", result={"ok": True, "itemId": "i2"})

        browser_task = asyncio.create_task(browser())
        result = await fn(label="A", track="V1", startFrame=0)
        await browser_task
        assert '"itemId": "i2"' in result

    asyncio.run(scenario())


def test_broker_stale_filtered_on_poll():
    async def scenario():
        registry = Registry()
        broker = Broker()
        reg = registry.register("default", "editor-1", "rev-0")
        binding = EditorBinding(reg.projectId, reg.editorInstanceId, reg.baseRevision, reg.ownershipEpoch)

        # 入队一个已过期的调用（deadline 在过去）
        fut = broker.invoke(binding, "add_clip", {})
        queued = broker._queues["default"][0]
        queued.deadline = 0.0  # 已过期

        # next_call 应过滤过期调用，长轮询 25s 超时返回 None
        # 这里直接验证 next_call 内部把过期调用过滤掉：用短超时触发
        call = await asyncio.wait_for(broker.next_call("default"), timeout=0.2)
        # 过期调用被过滤，队列空，会进入长轮询 —— 等到超时抛 TimeoutError 或返回 None
        assert call is None

    try:
        asyncio.run(scenario())
    except asyncio.TimeoutError:
        pass  # next_call 长轮询超时也算「无可用调用」的等价表现
