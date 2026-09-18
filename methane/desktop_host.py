"""Authenticated loopback transport for the installed desktop shell only."""

import hashlib
import hmac
import json
import os
import secrets
from http.cookies import SimpleCookie
from threading import Event
from urllib.parse import parse_qs

from starlette.middleware import Middleware
from starlette.responses import JSONResponse, RedirectResponse, Response


class DesktopSession:
    """Shared startup state; listening is not yet a ready Gradio application."""

    def __init__(self, token, instance, port):
        self.token, self.instance, self.port = token, instance, port
        self.ready = Event()
        self.stopping = Event()

    def middleware(self):
        return {"middleware": [Middleware(DesktopBoundary, session=self)]}

    def startup_client(self, http):
        session = self

        class StartupClient:
            def __getattr__(self, name):
                return getattr(http, name)

            def get(self, url, **kwargs):
                # Scoped to gradio.blocks during launch, not the global httpx
                # module. Never attach the owner credential to another URL.
                if url == f"http://127.0.0.1:{session.port}/gradio_api/startup-events":
                    kwargs["headers"] = {
                        **kwargs.get("headers", {}),
                        "x-dispatch-owner": session.token,
                    }
                    kwargs["trust_env"] = False
                    kwargs["follow_redirects"] = False
                return http.get(url, **kwargs)

        return StartupClient()


class DesktopBoundary:
    def __init__(self, app, *, session):
        self.session = session
        token, instance, port = session.token, session.instance, session.port
        self.app, self.token, self.instance = app, token, instance
        self.authority = f"127.0.0.1:{port}"
        self.origin = "http://" + self.authority
        self.proof = hashlib.sha256((token + ":" + instance).encode()).hexdigest()
        self.ticket_used = False
        self.cookie_name = "dispatch_desktop_" + hashlib.sha256(instance.encode()).hexdigest()[:16]

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        valid_origin = headers.get("origin") in (None, self.origin)
        valid_host = headers.get("host") == self.authority
        path = scope.get("path", "")

        async def reject(status=401):
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            return await JSONResponse(
                {"detail": "Open Dispatch Lab from its desktop application."}, status_code=status
            )(scope, receive, send)

        if not valid_host or not valid_origin:
            return await reject(403)
        if self.session.stopping.is_set():
            return await reject(503)
        if path == "/desktop/ready" and scope.get("method") == "GET":
            if not self.session.ready.is_set():
                return await reject(503)
            return await JSONResponse(dict(instance=self.instance, proof=self.proof))(
                scope, receive, send
            )
        if path == "/desktop/open" and scope.get("method") == "GET":
            if not self.session.ready.is_set():
                return await reject(503)
            ticket = parse_qs(scope.get("query_string", b"").decode()).get("key", [""])[0]
            if self.ticket_used or not hmac.compare_digest(ticket, self.token):
                return await reject()
            self.ticket_used = True
            response = RedirectResponse("/", status_code=303)
            # The shell starts at tauri://; Lax admits this first top-level GET
            # redirect. Explicit Host/Origin checks still protect every mutation.
            response.set_cookie(self.cookie_name, self.token, httponly=True, samesite="lax")
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store"
            return await response(scope, receive, send)
        # MCP has its own narrow session capability. It must never receive the
        # desktop owner cookie or any of the broad owner/UI endpoints.
        if path == "/dispatch/agent-control" and scope.get("method") == "POST":
            return await self.app(scope, receive, send)
        cookies = SimpleCookie()
        try:
            cookies.load(headers.get("cookie", ""))
        except Exception:
            return await reject()
        cookie = cookies.get(self.cookie_name)
        credential = headers.get("x-dispatch-owner", cookie.value if cookie else "")
        if not hmac.compare_digest(credential, self.token):
            return await reject()
        if path == "/desktop/status":
            from methane.processes import active_children

            app = scope.get("app")
            queue = app.get_blocks()._queue if hasattr(app, "get_blocks") else None
            ui_requests = (
                max(
                    queue.get_active_worker_count(),
                    sum(len(ids) for ids in queue.pending_event_ids_session.values()),
                )
                if queue
                else 0
            )
            return await JSONResponse(dict(workers=active_children(), ui_requests=ui_requests))(
                scope, receive, send
            )
        if path == "/desktop/stop" and scope.get("method") == "POST":
            import threading

            from methane.processes import stop_children

            def stop():
                stop_children()
                os._exit(0)

            self.session.stopping.set()
            threading.Timer(0.1, stop).start()
            return await Response(status_code=202)(scope, receive, send)
        await self.app(scope, receive, send)


def options(port):
    token = os.environ.pop("DISPATCH_DESKTOP_TOKEN", "")
    instance = os.environ.pop("DISPATCH_DESKTOP_INSTANCE", "")
    if not token or not instance:
        raise ValueError("Desktop launch requires its private instance handshake")
    return DesktopSession(token, instance, port)


def verify_release(root):
    """Build manifest accompanies the source; source identity needs no installed Git."""
    manifest = json.loads((root / "dispatch-release.json").read_text())
    if manifest["format"] != "dispatch-desktop-source/1":
        raise ValueError("Unsupported desktop resource manifest")
    for name, expected in manifest["files"].items():
        from pathlib import PurePosixPath

        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("Invalid release resource path")
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if not secrets.compare_digest(actual, expected):
            raise ValueError(f"Installed application resource changed: {name}")
    return manifest


def open_recording(path):
    """Read supported exports without extracting or executing archive contents."""
    import gzip
    import zipfile

    from methane.provenance import verify

    limit = 128 * 1024**2
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            candidates = [
                n
                for n in archive.namelist()
                if n in ("methane-run-v3.json", "methane-run-v2.json", "recorded-run.json.gz")
            ]
            if len(candidates) != 1:
                raise ValueError(
                    "Choose an individual recording export, not a multi-case project archive"
                )
            name = candidates[0]
            if archive.getinfo(name).file_size > limit:
                raise ValueError("Recording exceeds the desktop import limit")
            with archive.open(name) as stream:
                if name.endswith(".gz"):
                    with gzip.GzipFile(fileobj=stream) as uncompressed:
                        raw = uncompressed.read(limit + 1)
                else:
                    raw = stream.read(limit + 1)
    else:
        with gzip.open(path, "rb") as stream:
            raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Recording exceeds the desktop import limit")
    value = json.loads(raw)
    if value.get("schema_version") not in ("dispatch-lab/methane/2", "dispatch-lab/methane/3"):
        raise ValueError("Unsupported recording format; original file unchanged")
    return verify(value)
