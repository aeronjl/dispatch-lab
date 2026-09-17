"""Explicit, offline mappings from identified source bytes to compact observations."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np

CHANNELS = (
    "power_command",
    "stack_power",
    "smps_power",
    "subsystem_power",
    "chiller_power",
    "hydrogen_flow",
    "hydrogen_flow_cs",
)


def verified_bytes(directory, spec):
    path = Path(directory) / spec["filename"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        raise ValueError(f"Source bytes differ: {spec['filename']}; create a new dataset edition")
    return raw


def pem(directory, sources):
    """One-second signals → equal-weight stable plateau halves; no output-based filtering."""
    raw = {s["channel"]: verified_bytes(directory, s) for s in sources}
    values = {c: np.array([float(v) for v in raw[c].splitlines()]) for c in CHANNELS}
    times = [
        datetime.strptime(t, "%d-%b-%Y %H:%M:%S") for t in raw["timestamp"].decode().splitlines()
    ]
    size = len(times)
    if size < 2 or any(len(v) != size or not np.isfinite(v).all() for v in values.values()):
        raise ValueError("All source channels must be finite, synchronized and equally long")
    if any((b - a).total_seconds() != 1 for a, b in zip(times, times[1:], strict=False)):
        raise ValueError(
            "Source timestamps must be consecutive one-second samples; no implicit filling"
        )
    values["system_power"] = (
        values["smps_power"] + values["subsystem_power"] + values["chiller_power"]
    )
    starts = [0, *(np.flatnonzero(np.diff(values["power_command"])) + 1).tolist(), size]
    rows, segments = [], []
    for segment, (start, stop) in enumerate(zip(starts, starts[1:], strict=False)):
        count = stop - start
        kept = bool(count >= 900 and values["power_command"][start] > 0)
        segments.append(
            dict(
                segment=segment,
                first_index=start,
                stop_index=stop,
                samples=count,
                retained=kept,
                reason="stable halves after 120 s"
                if kept
                else "short or off segment; not a startup fit",
            )
        )
        if not kept:
            continue
        begin = start + 120
        split = begin + (stop - begin) // 2
        for label, a, b in (("development", begin, split), ("evaluation", split, stop)):
            rows.append(
                dict(
                    segment=segment,
                    split=label,
                    n=b - a,
                    first_index=a,
                    stop_index=b,
                    start=times[a].isoformat(),
                    end=times[b - 1].isoformat(),
                    **{c: float(v[a:b].mean()) for c, v in values.items()},
                )
            )
    if len(rows) < 6:
        raise ValueError("At least three retained plateaus are needed")
    return dict(
        rows=rows, segments=segments, samples=size, retained_samples=sum(r["n"] for r in rows)
    )


def reactor(directory, sources):
    """Retain the authored pixel extraction; never call these raw sensor observations."""
    raw = {s["channel"]: verified_bytes(directory, s) for s in sources}
    picks = json.loads(raw["digitization"])
    return dict(
        rows=[
            dict(
                index=i,
                x_pixel=x,
                y_pixel=y,
                time_minutes=(x - 174) * 40 / (539 - 174),
                temperature_c=260 + (358 - y) * 80 / (358 - 134),
                split="descriptive",
            )
            for i, (x, y) in enumerate(picks["temperature_pixels"])
        ],
        mapping=picks["method"],
        samples=len(picks["temperature_pixels"]),
    )


def rebuild(profile, directory):
    adapter = {"csu-pem/1": pem, "kit-slurry/1": reactor}[profile["adapter"]]
    return adapter(directory, profile["raw_sources"])
