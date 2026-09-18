"""Native process checks run on each build host; never mock a Windows pass."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from methane.paths import data_path, user_home
from methane.processes import lease, peak_memory_bytes, popen_leased, spawn

ROOT = Path(__file__).resolve().parents[1]


def wait_for(path, proc):
    deadline = time.monotonic() + 10
    while not path.exists():
        assert proc.poll() is None, proc.returncode
        assert time.monotonic() < deadline
        time.sleep(0.02)


def test_workspace_paths_are_separate_and_overrides_preserved(monkeypatch, tmp_path):
    monkeypatch.setenv("DISPATCH_DATA_ROOT", str(tmp_path / "work space ü"))
    assert data_path("weather") == tmp_path / "work space ü" / "weather"
    monkeypatch.setenv("DISPATCH_WEATHER_DIR", str(tmp_path / "original-weather"))
    assert data_path("weather", "DISPATCH_WEATHER_DIR") == tmp_path / "original-weather"
    assert user_home("darwin", {"HOME": str(tmp_path)}).parts[-3:] == (
        "Library",
        "Application Support",
        "org.dispatchlab.desktop",
    )
    assert (
        user_home("win32", {"LOCALAPPDATA": str(tmp_path)}) == tmp_path / "org.dispatchlab.desktop"
    )


def test_native_lease_exclusion_and_release(tmp_path):
    with lease(tmp_path / "slot"):
        with pytest.raises(BlockingIOError):
            lease(tmp_path / "slot")
    with lease(tmp_path / "slot"):
        pass


def test_worker_holds_lease_after_parent_releases_then_dies(tmp_path):
    # Parent exit closes every parent-side handle. The worker alone retains the
    # inherited open description/HANDLE. No PID lookup is used to decide ownership.
    script = """
import sys, json
from pathlib import Path
from methane.processes import lease, popen_leased
root=Path(sys.argv[1])
with lease(root/'slot') as handle:
    child=popen_leased([sys.executable, '-c', "import time; time.sleep(30)"], leases=(handle,))
    (root/'pid').write_text(str(child.pid))
"""
    parent = subprocess.Popen([sys.executable, "-c", script, str(tmp_path)], cwd=ROOT)
    try:
        wait_for(tmp_path / "pid", parent)
        assert parent.wait(timeout=10) == 0
        with pytest.raises(BlockingIOError):
            lease(tmp_path / "slot")
    finally:
        if (tmp_path / "pid").exists():
            pid = int((tmp_path / "pid").read_text())
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.OpenProcess(1, False, pid)
                assert handle
                kernel.TerminateProcess(handle, 1)
                kernel.CloseHandle(handle)
            else:
                import signal

                os.kill(pid, signal.SIGKILL)
        if parent.poll() is None:
            parent.kill()
            parent.wait()
    deadline = time.monotonic() + 10
    while True:
        try:
            with lease(tmp_path / "slot"):
                break
        except BlockingIOError:
            assert time.monotonic() < deadline
            time.sleep(0.02)


def test_unrelated_child_does_not_inherit_other_leases(tmp_path):
    with lease(tmp_path / "other"):
        child = popen_leased([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with lease(tmp_path / "other"):
            pass
    finally:
        child.kill()
        child.wait()


def test_worker_entry_points_are_explicit():
    with pytest.raises(ValueError, match="Unknown"):
        spawn("untrusted_module")
    assert peak_memory_bytes() > 0


def test_self_owned_wall_budget_without_parent_monitor(tmp_path):
    state = tmp_path / "state.json"
    script = "from methane.worker_budget import budget; from pathlib import Path; import sys,time; budget(1,Path(sys.argv[1])); time.sleep(30)"
    p = subprocess.run([sys.executable, "-c", script, str(state)], cwd=ROOT, timeout=15)
    assert p.returncode == 124
    assert json.loads(state.read_text())["status"] == "time-limited"


def test_shutdown_prevents_a_late_worker_launch():
    script = """
from methane.processes import spawn, stop_children
stop_children()
try:
    spawn('methane.control_worker')
except RuntimeError as e:
    assert 'stopping' in str(e)
else:
    raise AssertionError('Late worker launched during shutdown')
"""
    subprocess.run([sys.executable, "-c", script], cwd=ROOT, check=True, timeout=10)
