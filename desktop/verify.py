"""Exercise the private runtime from a relocated path without developer PATH."""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def server_check(payload, python, workspace, env, base):
    """Actual Gradio launch/handshake, separate from native first-frame timing."""
    import httpx

    samples = []
    for _ in range(2):
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        token, instance = secrets.token_hex(32), secrets.token_hex(16)
        started = time.monotonic()
        with (base / f"startup-{instance}.log").open("wb") as log:
            process = subprocess.Popen(
                [
                    str(python),
                    "-s",
                    str(payload / "source/desktop_entry.py"),
                    "serve",
                    "--workspace",
                    str(workspace),
                    "--port",
                    str(port),
                ],
                cwd=base,
                env={**env, "DISPATCH_DESKTOP_TOKEN": token, "DISPATCH_DESKTOP_INSTANCE": instance},
                stdout=log,
                stderr=log,
            )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=10
            ) as browser:
                while True:
                    assert process.poll() is None, f"Packaged server exited {process.returncode}"
                    if time.monotonic() - started > 90:
                        raise TimeoutError("Packaged Gradio startup did not complete")
                    try:
                        ready = browser.get("/desktop/ready")
                        if ready.status_code == 200:
                            break
                    except httpx.RequestError:
                        pass
                    time.sleep(0.1)
                assert ready.json() == dict(
                    instance=instance,
                    proof=hashlib.sha256(f"{token}:{instance}".encode()).hexdigest(),
                )
                seconds = time.monotonic() - started
                assert browser.get("/").status_code == 401
                assert browser.get("/gradio_api/startup-events").status_code == 401
                assert (
                    browser.get(f"/desktop/open?key={token}", follow_redirects=True).status_code
                    == 200
                )
                assert browser.get("/config").json()["components"]
                assert (
                    browser.post(
                        "/desktop/stop", headers={"Origin": "https://untrusted.example"}
                    ).status_code
                    == 403
                )
                assert browser.post("/desktop/stop").status_code == 202
                assert process.wait(timeout=15) == 0
                samples.append(seconds)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    return dict(
        scope="Two packaged backend starts; readiness after Gradio initialization, excludes native window rendering and installer cold cache",
        seconds=samples,
    )


async def mcp(executable):
    from mcp.client import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async with stdio_client(
        StdioServerParameters(
            command=str(executable.resolve()),
            args=["--mcp"],
            env={"DISPATCH_AGENT_TOKEN": "", "DISPATCH_CONTROL_SESSION": ""},
        )
    ) as streams:
        async with ClientSession(*streams) as session:
            hello = await session.initialize()
            assert hello.server_info.name == "Dispatch Lab"
            tools = {tool.name for tool in (await session.list_tools()).tools}
            assert tools == {"observe", "preview_reference", "preview_actions", "advance", "trace"}
            assert (await session.call_tool("observe")).is_error
    return dict(
        status="passed",
        scope="Installed executable stdio discovery; no implicit authority",
        tools=sorted(tools),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mcp-executable", type=Path)
    args = parser.parse_args()
    output = ROOT / "build" / "desktop"
    if args.mcp_executable:
        result = asyncio.run(mcp(args.mcp_executable))
        executable = args.mcp_executable.resolve()
        payload = executable.parent / (
            "../Resources/payload" if sys.platform == "darwin" else "payload"
        )
        result["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
        result["source_manifest"] = json.loads(
            (payload / "source/dispatch-release.json").read_text()
        )
        result["runtime"] = json.loads((payload / "runtime.json").read_text())
        (output / "mcp-report.json").write_text(json.dumps(result, indent=2))
        print(json.dumps({k: result[k] for k in ("status", "scope", "executable_sha256")}))
        return
    source = output / "payload"
    with tempfile.TemporaryDirectory(prefix="Dispatch relocation ü ") as temporary:
        base = Path(temporary)
        payload = base / "application files"
        shutil.copytree(source, payload, symlinks=True)
        python = payload / "python" / ("python.exe" if os.name == "nt" else "bin/python3.12")
        workspace = base / "user workspace"
        # No executable search path: every private interpreter launch is explicit.
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("PYTHON", "DISPATCH_", "VIRTUAL_ENV"))
        }
        no_tools = base / "empty executable search path"
        no_tools.mkdir()
        env.update(
            PATH=str(no_tools), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1"
        )
        assert all(
            shutil.which(name, path=env["PATH"]) is None
            for name in ("python", "python3", "uv", "git", "node")
        )
        # Deny application writes on POSIX; Windows read-only directory attributes
        # are not an equivalent ACL test and are not represented as one.
        if os.name != "nt":
            for p in payload.rglob("*"):
                if not p.is_symlink():
                    p.chmod(p.stat().st_mode & ~0o222)
        began = time.monotonic()
        try:
            subprocess.run(
                [
                    str(python),
                    "-s",
                    str(payload / "source/desktop_entry.py"),
                    "check",
                    "--workspace",
                    str(workspace),
                ],
                cwd=base,
                env=env,
                check=True,
                timeout=180,
            )
            report = json.loads((workspace / "desktop-smoke/report.json").read_text())
            report["startup"] = server_check(payload, python, workspace, env, base)
            report.update(
                relocation=True,
                developer_path_removed=True,
                read_only_resources=os.name != "nt",
                elapsed_seconds=time.monotonic() - began,
            )
            (output / "relocation-report.json").write_text(json.dumps(report, indent=2))
            print(
                json.dumps(
                    {k: report[k] for k in ("status", "platform", "relocation", "elapsed_seconds")}
                )
            )
        finally:
            if os.name != "nt":
                for p in payload.rglob("*"):
                    if not p.is_symlink():
                        p.chmod(p.stat().st_mode | 0o200)


if __name__ == "__main__":
    main()
