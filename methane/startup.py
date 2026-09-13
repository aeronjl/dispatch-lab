"""Local Gradio launch with a bounded cold-archive readiness allowance.

Gradio's installed networking.url_ok aborts on its first three-second timeout.
The existing archive's initial root response was measured at 3.67 seconds. There
is no public launch parameter for this check: override only this compatibility
hook during launch, then restore it before normal serving. A failed response
remains a failed launch; no public share or frontend-check bypass is introduced.
"""

from threading import RLock
from urllib.parse import urlsplit

import gradio.networking
import httpx

_lock = RLock()
_READY = frozenset((200, 401, 301, 302, 303, 307, 308))
LOCAL_READINESS_SECONDS = 10


def local_ready(url, original):
    address = urlsplit(url)
    if address.scheme != "http" or address.hostname not in ("127.0.0.1", "localhost", "::1"):
        return original(url)
    try:
        # Only literal loopback hosts enter here. A site/organization proxy
        # cannot establish whether this local application is ready.
        with httpx.Client(trust_env=False) as client:
            response = client.head(url, timeout=LOCAL_READINESS_SECONDS)
        return response.status_code in _READY
    except (httpx.RequestError, ConnectionError):
        return False


def launch_local(application, **options):
    """Preserve launch validation and restore the hook even on startup failure."""
    if (
        options.get("server_name") not in ("127.0.0.1", "localhost", "::1")
        or options.get("share") is not False
    ):
        raise ValueError("This startup allowance is for explicit local-only launches")
    if "prevent_thread_lock" in options:
        raise ValueError("launch_local owns the server lifetime")
    with _lock:
        original = gradio.networking.url_ok
        gradio.networking.url_ok = lambda url: local_ready(url, original)
        try:
            result = application.launch(**options, prevent_thread_lock=True)
        except Exception:
            application.close()
            raise
        finally:
            gradio.networking.url_ok = original
    application.block_thread()
    return result
