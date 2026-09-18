"""Worker-owned limits remain effective after the UI process disappears."""

import json
import os
import threading
import time

from methane.processes import peak_memory_bytes

_windows_jobs = []


def _cpu_limit(seconds, memory_bytes):
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds + 1))
        return
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong),
            ("job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD),
            ("min_set", ctypes.c_size_t),
            ("max_set", ctypes.c_size_t),
            ("active_processes", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", ctypes.c_ulonglong * 6),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t),
            ("peak_job_memory", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = Extended()
    limits.basic.process_time = seconds * 10_000_000
    limits.basic.flags = 0x2 | (0x100 if memory_bytes else 0)
    limits.process_memory = memory_bytes or 0
    if not kernel.SetInformationJobObject(
        handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
    ) or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel.CloseHandle(handle)
        raise ctypes.WinError(error)
    _windows_jobs.append(handle)


def budget(seconds, status_path, memory_bytes=2 * 1024**3, *, cpu=True):
    """CPU is OS-enforced; wall/peak-memory watchdog polls every 0.1 s.

    Windows also has a hard process-commit memory cap. POSIX memory enforcement is a
    sampled peak-RSS cap, not an address-space guarantee. Never describe them as equal.
    """
    if cpu:
        _cpu_limit(seconds, memory_bytes)
    stopped = threading.Event()
    started = time.monotonic()

    def watch():
        while not stopped.wait(0.1):
            reason = None
            if time.monotonic() - started >= seconds:
                reason = "Worker wall budget exhausted"
            elif memory_bytes and peak_memory_bytes() > memory_bytes:
                reason = "Worker memory budget exhausted"
            if reason:
                try:
                    from methane.siting.store import atomic

                    atomic(
                        status_path,
                        json.dumps(dict(status="time-limited", description=reason)).encode(),
                    )
                finally:
                    os._exit(124)

    threading.Thread(target=watch, name="dispatch-worker-budget", daemon=True).start()
    return stopped
