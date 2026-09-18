"""Portable OS-owned leases and explicitly named Python workers.

POSIX flock leases follow an inherited open file description. On Windows an
exclusive CreateFile handle (share mode zero) follows inherited handle lifetime.
Unlike Windows byte-range locks, that exclusion survives the parent's exit.
There is no unlock/relock handoff window and no PID or stale-file based ownership.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

_inherit_lock = threading.Lock()
_children_lock = threading.RLock()
_children = []
_stopping = False
WORKERS = frozenset(
    {
        "methane.batch_worker",
        "methane.control_worker",
        "methane.learning_worker",
        "methane.service_alternatives_worker",
        "methane.study_worker",
        "methane.control_session_worker",
        "methane.control_replay",
        "methane.siting.production",
        "methane.learning_lab.jobs",
    }
)


def lease(path, *, blocking=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        import fcntl

        handle = path.open("a+b")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            return handle
        except BaseException:
            handle.close()
            raise
    import ctypes
    import msvcrt
    from ctypes import wintypes

    create = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    while True:
        handle = create(str(path.resolve()), 0xC0000000, 0, None, 4, 0x80, None)
        if handle != ctypes.c_void_p(-1).value:
            return os.fdopen(
                msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY), "r+b", buffering=0
            )
        error = ctypes.get_last_error()
        if error not in (32, 33):
            raise ctypes.WinError(error)
        if not blocking:
            raise BlockingIOError("Another worker owns this lease")
        time.sleep(0.02)


def popen_leased(args, *, leases=(), **kwargs):
    """Inherit only the leases specified by this launch, not other workers' locks."""
    kwargs.setdefault("close_fds", True)
    if os.name != "nt":
        return subprocess.Popen(args, pass_fds=tuple(x.fileno() for x in leases), **kwargs)
    import msvcrt

    kwargs.pop("start_new_session", None)
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
    handles = [msvcrt.get_osfhandle(x.fileno()) for x in leases]
    info = subprocess.STARTUPINFO()
    info.lpAttributeList = {"handle_list": handles}
    with _inherit_lock:
        try:
            for handle in handles:
                os.set_handle_inheritable(handle, True)
            return subprocess.Popen(args, startupinfo=info, **kwargs)
        finally:
            for handle in handles:
                os.set_handle_inheritable(handle, False)


def spawn(module, arguments=(), **kwargs):
    if module not in WORKERS:
        raise ValueError("Unknown Dispatch Lab worker entry point")
    # The desktop ships a real private interpreter, preserving captured-source -m.
    if getattr(sys, "frozen", False):
        raise RuntimeError("Worker execution requires the bundled Python interpreter")
    with _children_lock:
        if _stopping:
            raise RuntimeError("The desktop runtime is stopping; no new worker was launched")
        child = popen_leased([sys.executable, "-m", module, *map(str, arguments)], **kwargs)
        _children[:] = [p for p in _children if p.poll() is None]
        _children.append(child)
    return child


def peak_memory_bytes():
    if os.name != "nt":
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    query = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.PeakWorkingSetSize


def active_children():
    with _children_lock:
        return sum(p.poll() is None for p in _children)


def stop_children():
    global _stopping
    with _children_lock:
        _stopping = True
        children = list(_children)
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
