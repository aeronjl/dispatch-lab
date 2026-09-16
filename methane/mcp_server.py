"""Stdio MCP bridge to one explicitly granted local simulation session.

Run: uv run python -m methane.mcp_server. All stdout belongs to MCP.
"""

import os
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from methane.control_port import VERSION, Actions

server = MCPServer(
    "Dispatch Lab",
    version=VERSION,
    instructions="Control one bounded SIMULATED plant session granted by its owner. Observe first. Preview a reference or explicit action, inspect the prediction, then advance using that proposal and observation revision. Report requested versus applied delivery, constraints and solver limitations. Never infer sensor truth or claim hardware access. If disconnected, revoked or expired, stop; do not seek other credentials. Services and protected recovery remain under the reference executive.",
)
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


async def call(operation, **values):
    url = os.environ.get("DISPATCH_CONTROL_URL", "http://127.0.0.1:7860")
    parts = urlsplit(url)
    if (
        parts.scheme != "http"
        or parts.hostname not in ("127.0.0.1", "localhost", "::1")
        or parts.username
        or parts.password
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError("DISPATCH_CONTROL_URL must be a local HTTP app origin")
    session = os.environ.get("DISPATCH_CONTROL_SESSION", "")
    token = os.environ.get("DISPATCH_AGENT_TOKEN", "")
    if not session or not token:
        raise ValueError("Open Agent control in the app and grant this session a capability first")
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30) as client:
        response = await client.post(
            url.rstrip("/") + "/dispatch/agent-control",
            json=dict(operation=operation, session_id=session, credential=token, **values),
        )
    if not response.is_success:
        raise ValueError(response.json().get("detail", "Control request rejected"))
    return response.json()


@server.tool(annotations=READ)
async def observe() -> dict[str, Any]:
    """Read the current observation, estimates, constraints, reference plan and authority. Never advances time."""
    return await call("observe")


@server.tool(annotations=READ)
async def preview_reference(revision: int) -> dict[str, Any]:
    """Preview the configured reference policy at this decision. Returns a proposal ID and predicted trajectory; not execution."""
    return await call("preview", revision=revision)


@server.tool(annotations=READ)
async def preview_actions(revision: int, actions: Actions) -> dict[str, Any]:
    """Preview six dispatch requests for one hourly interval. kW except methane_kg (kg CH4). Infeasible requests are rejected or visibly projected within limits. No time advances."""
    return await call("preview", revision=revision, actions=actions.model_dump())


@server.tool(annotations=WRITE)
async def advance(revision: int, proposal_id: str, request_id: str, reason: str) -> dict[str, Any]:
    """Advance one simulated interval using a reviewed proposal. Provide a unique request ID and concise evidence-based reason. Retry uncertain responses with the SAME IDs. Poll observe for receipt before proceeding. Changes this session only."""
    return await call(
        "advance", revision=revision, proposal_id=proposal_id, request_id=request_id, reason=reason
    )


@server.tool(annotations=READ)
async def trace() -> dict[str, Any]:
    """Read completed action receipts: attribution, requests, applied commands, observed outcomes, solver status and balance checks."""
    return await call("trace")


if __name__ == "__main__":
    server.run(transport="stdio")
