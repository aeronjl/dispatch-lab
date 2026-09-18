import hashlib
import json

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from methane.desktop_host import DesktopBoundary, DesktopSession, open_recording, verify_release


def client(instance="a", ready=True):
    async def result(request):
        return JSONResponse({"owner": True})

    session = DesktopSession("secret", instance, 9876)
    if ready:
        session.ready.set()
    return TestClient(
        Starlette(
            routes=[Route("/", result), Route("/dispatch/agent-control", result, methods=["POST"])],
            middleware=[Middleware(DesktopBoundary, session=session)],
        ),
        base_url="http://127.0.0.1:9876",
    )


def test_listening_is_not_ready_and_startup_endpoint_is_not_public():
    c = client(ready=False)
    assert c.get("/desktop/ready").status_code == 503
    assert c.get("/desktop/open?key=secret").status_code == 503
    assert c.get("/gradio_api/startup-events").status_code == 401


def test_internal_startup_authentication_is_exact_url_only():
    from types import SimpleNamespace

    requests = []
    http = SimpleNamespace(get=lambda url, **kwargs: requests.append((url, kwargs)))
    session = DesktopSession("secret", "test", 9876)
    scoped = session.startup_client(http)
    scoped.get("http://127.0.0.1:9876/gradio_api/startup-events", timeout=None)
    scoped.get("http://127.0.0.1:9877/gradio_api/startup-events")
    scoped.get("https://example.org/")
    assert requests[0][1]["headers"] == {"x-dispatch-owner": "secret"}
    assert requests[0][1]["follow_redirects"] is False
    assert requests[0][1]["trust_env"] is False
    assert requests[1][1] == requests[2][1] == {}


def test_handshake_proves_instance_without_disclosing_owner_token():
    c = client()
    assert c.get("/").status_code == 401
    ready = c.get("/desktop/ready").json()
    assert ready == dict(instance="a", proof=hashlib.sha256(b"secret:a").hexdigest())
    assert "secret" not in json.dumps(ready)
    assert c.get("/desktop/open?key=wrong").status_code == 401
    response = c.get("/desktop/open?key=secret")
    assert response.status_code == 200
    assert response.history[0].headers["referrer-policy"] == "no-referrer"
    assert "HttpOnly" in response.history[0].headers["set-cookie"]
    assert c.get("/desktop/open?key=secret").status_code == 401
    assert c.get("/", headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert c.get("/", headers={"Host": "untrusted.example:9876"}).status_code == 403


def test_only_narrow_mcp_route_bypasses_desktop_cookie():
    c = client()
    assert c.post("/dispatch/agent-control").status_code == 200
    assert c.post("/dispatch/control-session").status_code == 401
    assert c.post("/dispatch/agent-control", headers={"Origin": "null"}).status_code == 403
    assert c.get("/desktop/status").status_code == 401


def test_close_status_counts_gradio_work_as_well_as_child_processes():
    from types import SimpleNamespace

    c = client()
    queue = SimpleNamespace(
        get_active_worker_count=lambda: 1,
        pending_event_ids_session={"session": {"active", "queued"}},
    )
    c.app.get_blocks = lambda: SimpleNamespace(_queue=queue)
    answer = c.get("/desktop/status", headers={"x-dispatch-owner": "secret"}).json()
    assert answer["ui_requests"] == 2


def test_instance_cookies_do_not_collide_across_ports_or_grant_other_instances():
    first, second = client("first"), client("second")
    first.get("/desktop/open?key=secret")
    second.cookies.update(first.cookies)
    assert second.get("/").status_code == 401
    second.get("/desktop/open?key=secret")
    assert len(second.cookies) == 2


def test_installed_source_tampering_and_invalid_paths_fail(tmp_path):
    (tmp_path / "file.py").write_bytes(b"original")
    value = dict(
        format="dispatch-desktop-source/1",
        files={"file.py": hashlib.sha256(b"original").hexdigest()},
    )
    manifest = tmp_path / "dispatch-release.json"
    manifest.write_text(json.dumps(value))
    assert verify_release(tmp_path) == value
    (tmp_path / "file.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        verify_release(tmp_path)
    value["files"] = {"../file.py": "bad"}
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="Invalid"):
        verify_release(tmp_path)


def test_multicase_zip_is_not_extracted_or_executed(tmp_path):
    import zipfile

    path = tmp_path / "untrusted.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../../escaped", "bad")
        archive.writestr("source/anything.py", "raise Exception('never execute')")
    with pytest.raises(ValueError, match="individual recording"):
        open_recording(path)
    assert not (tmp_path.parent / "escaped").exists()


def test_real_gradio_launch_completes_authenticated_startup(monkeypatch):
    import socket

    import gradio as gr
    import gradio.blocks
    import httpx

    from methane.startup import launch_local

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    session = DesktopSession("local-test-secret", "launch", port)
    original_http = gradio.blocks.httpx
    with gr.Blocks(analytics_enabled=False) as application:
        gr.Markdown("Desktop startup fixture")

    def inspect_running():
        assert session.ready.is_set()
        assert gradio.blocks.httpx is original_http
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as browser:
            assert browser.get("/desktop/ready").status_code == 200
            assert browser.get("/gradio_api/startup-events").status_code == 401
            response = browser.get("/desktop/open?key=local-test-secret", follow_redirects=True)
            assert response.status_code == 200
            assert browser.get("/config").json()["components"]

    monkeypatch.setattr(application, "block_thread", inspect_running)
    try:
        launch_local(
            application,
            desktop_session=session,
            app_kwargs=session.middleware(),
            server_name="127.0.0.1",
            server_port=port,
            share=False,
            quiet=True,
        )
    finally:
        application.close()
