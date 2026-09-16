"""Browser fixture's actual MCP client: advance exactly one granted test interval."""

import asyncio
import json
import os
import sys

from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    async with stdio_client(
        StdioServerParameters(
            command=sys.executable,
            args=["-m", "methane.mcp_server"],
            env={k: v for k, v in os.environ.items() if k.startswith("DISPATCH_")},
        )
    ) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()

            async def tool(name, args=None):
                value = await session.call_tool(name, args)
                if value.is_error:
                    raise ValueError(str(value.content))
                return value.structured_content

            observed = await tool("observe")
            revision = observed["state"]["revision"]
            preview = await tool("preview_reference", {"revision": revision})
            accepted = await tool(
                "advance",
                dict(
                    revision=revision,
                    proposal_id=preview["proposal_id"],
                    request_id="mcp-browser-check",
                    reason="Follow the bounded reference plan <script>unsafe</script>",
                ),
            )
            print(
                json.dumps(dict(observed_hour=observed["observation"]["hour"], accepted=accepted))
            )


if __name__ == "__main__":
    asyncio.run(main())
