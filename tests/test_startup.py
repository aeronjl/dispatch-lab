"""Cold local startup keeps actual HTTP readiness and scopes its compatibility hook."""

from types import SimpleNamespace

import gradio.networking
import httpx
import pytest

from methane.startup import launch_local, local_ready


@pytest.mark.parametrize(
    "code, expected",
    [(200, True), (401, True), (307, True), (403, False), (500, False), (503, False)],
)
def test_local_readiness_requires_a_supported_real_response(monkeypatch, code, expected):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs == dict(trust_env=False)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def head(self, url, timeout):
            calls.append((url, timeout))
            return SimpleNamespace(status_code=code)

    monkeypatch.setattr(httpx, "Client", Client)
    assert local_ready("http://127.0.0.1:7860/", lambda _: False) is expected
    assert calls == [("http://127.0.0.1:7860/", 10)]


def test_timeout_is_not_replaced_by_an_assumed_success(monkeypatch):
    def failed(**kwargs):
        raise httpx.ReadTimeout("Local server did not respond")

    monkeypatch.setattr(httpx, "Client", failed)
    assert not local_ready("http://localhost:7860/", lambda _: True)
    calls = []
    assert local_ready("https://example.org/", lambda url: calls.append(url) or True)
    assert calls == ["https://example.org/"]


@pytest.mark.parametrize("fails", [False, True])
def test_compatibility_hook_is_restored_before_serving_or_propagating_failure(fails):
    original, calls = gradio.networking.url_ok, []

    class Application:
        def launch(self, **options):
            assert options["prevent_thread_lock"]
            assert gradio.networking.url_ok is not original
            if fails:
                raise ValueError("Server was not ready")
            return "local server"

        def close(self):
            calls.append("close")

        def block_thread(self):
            assert gradio.networking.url_ok is original
            calls.append("serve")

    if fails:
        with pytest.raises(ValueError, match="not ready"):
            launch_local(Application(), server_name="127.0.0.1", share=False)
    else:
        assert launch_local(Application(), server_name="127.0.0.1", share=False) == "local server"
    assert calls == (["close"] if fails else ["serve"])
    assert gradio.networking.url_ok is original


def test_public_launch_cannot_use_the_local_exception():
    with pytest.raises(ValueError, match="local-only"):
        launch_local(None, server_name="0.0.0.0", share=True)
