"""Application resources are immutable; installed workspaces live outside the app.

Developer defaults preserve the existing repository layout. Desktop bootstrap sets
DISPATCH_DATA_ROOT before importing any store or provenance module. Frozen workers
inherit that workspace while their resource root remains their captured source.
"""

import os
import sys
from pathlib import Path


def resource_root():
    return Path(__file__).resolve().parent.parent


def user_home(platform=None, environ=None):
    platform = sys.platform if platform is None else platform
    env = os.environ if environ is None else environ
    home = Path(env.get("USERPROFILE" if platform == "win32" else "HOME", str(Path.home())))
    if platform == "win32":
        return (
            Path(env.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
            / "org.dispatchlab.desktop"
        )
    if platform == "darwin":
        return home / "Library" / "Application Support" / "org.dispatchlab.desktop"
    return Path(env.get("XDG_DATA_HOME", str(home / ".local" / "share"))) / "dispatch-lab"


def data_root():
    return Path(os.environ.get("DISPATCH_DATA_ROOT", resource_root() / "runs")).resolve()


def data_path(name, override=None):
    return Path(
        os.environ.get(override, data_root() / name) if override else data_root() / name
    ).resolve()


def cache_root():
    return Path(os.environ.get("DISPATCH_CACHE_ROOT", data_root() / "cache")).resolve()


def bootstrap(workspace=None):
    root = Path(workspace).expanduser().resolve() if workspace else user_home() / "workspace"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.environ["DISPATCH_DATA_ROOT"] = str(root)
    os.environ.setdefault("GRADIO_TEMP_DIR", str(root / "cache" / "gradio"))
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return root
