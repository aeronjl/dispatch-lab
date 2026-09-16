"""Real stdio protocol handshake plus restricted local bridge transport."""

import asyncio
import sys

import httpx
import pytest
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from methane import mcp_server


def test_real_stdio_protocol_discovery_and_no_implicit_authority():
    async def exercise():
        async with stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "methane.mcp_server"],
                env={"DISPATCH_AGENT_TOKEN": "", "DISPATCH_CONTROL_SESSION": ""},
            )
        ) as streams:
            async with ClientSession(*streams) as session:
                info = await session.initialize()
                assert info.server_info.name == "Dispatch Lab"
                tools = (await session.list_tools()).tools
                assert {t.name for t in tools} == {
                    "observe",
                    "preview_reference",
                    "preview_actions",
                    "advance",
                    "trace",
                }
                advance = next(t for t in tools if t.name == "advance")
                assert not advance.annotations.read_only_hint
                assert all(t.output_schema is not None for t in tools)
                assert (await session.call_tool("observe")).is_error

    asyncio.run(exercise())


def test_bridge_only_calls_bound_session_no_redirects_or_environment_proxy(monkeypatch):
    monkeypatch.setenv("DISPATCH_CONTROL_SESSION", "a" * 32)
    monkeypatch.setenv("DISPATCH_AGENT_TOKEN", "private-test-token")
    monkeypatch.setenv("DISPATCH_CONTROL_URL", "http://127.0.0.1:7860")
    calls = []
    original = httpx.AsyncClient

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "waiting"})

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return original(**kwargs, transport=httpx.MockTransport(transport))

    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", client)
    assert asyncio.run(mcp_server.observe())["status"] == "waiting"
    assert str(calls[0].url) == "http://127.0.0.1:7860/dispatch/agent-control"
    assert b'"session_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' in calls[0].content
    monkeypatch.setenv("DISPATCH_CONTROL_URL", "https://example.com")
    with pytest.raises(ValueError, match="local HTTP"):
        asyncio.run(mcp_server.observe())
