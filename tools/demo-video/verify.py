"""Check the delivered film and saved presentation inputs without re-solving."""

import gzip
import hashlib
import json
import math
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORY = json.loads((ROOT / "tools/demo-video/storyboard.json").read_text())
BASE = ROOT / "build/demo-video" / STORY["output"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a, b):
    return math.isclose(a, b, abs_tol=1e-6, rel_tol=1e-8)


def main():
    movie = BASE.with_suffix(".mp4")
    manifest = json.loads(Path(f"{BASE}-manifest.json").read_text())
    fixture = json.loads(gzip.decompress((ROOT / STORY["control_fixture"]).read_bytes()))
    motion = json.loads(gzip.decompress((ROOT / STORY["fixture"]).read_bytes()))
    packet, comparison = fixture["input_packet"], fixture["comparison"]
    checks = []

    require(manifest["storyboard"] == STORY, "Storyboard differs from captured film")
    require(not manifest["errors"] and not manifest["network_requests"], "Capture errors/network")
    for source in (manifest["source"], manifest["control_source"]):
        require(sha(ROOT / source["fixture"]) == source["sha256"], "Fixture hash differs")
    require(fixture["source_run_id"] == motion["source_run_id"], "Run identities differ")
    require(fixture["source_integrity"] == motion["source_integrity"], "Archive identities differ")
    require(fixture["motion_excerpt_sha256"] == sha(ROOT / STORY["fixture"]), "Excerpt differs")
    for folder, key in (
        (ROOT, "presentation_source_sha256"),
        (Path(__file__).parent, "film_source_sha256"),
    ):
        for name, expected in manifest[key].items():
            require(sha(folder / name) == expected, f"Capture source changed: {name}")
    checks.append("Captured source, fixtures and offline rendering identities match")

    operands = {k: v for k, v in packet.items() if k != "information_id"}
    identity = hashlib.sha256(
        json.dumps(operands, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    require(
        identity == packet["information_id"] == comparison["information_id"], "Information differs"
    )
    require(packet["state"] == comparison["initial"], "Starting state differs")
    require(packet["cost_version"] == comparison["cost_version"], "Dispatch prices differ")
    require(
        packet["forecast"]["source"] == comparison["forecast_source"], "Forecast source differs"
    )
    require(comparison["status"] == "complete", "Comparison is incomplete")
    require(
        set(comparison["predictions"]) == {"Greedy", "MPC · methane", "MPC · economics"},
        "Missing policy",
    )
    for name, prediction in comparison["predictions"].items():
        require(prediction["information_id"] == identity, f"Different policy inputs: {name}")
        points, totals = prediction["points"], prediction["predicted"]
        require(len(points) == len(packet["forecast"]["times"]), "Different horizon")
        energy = packet["state"]["battery_kwh"]
        efficiency = math.sqrt(packet["plant"]["roundtrip_efficiency"])
        for i, point in enumerate(points):
            require(point["time"] == packet["forecast"]["times"][i], "Different forecast interval")
            for field in ("pv_kw", "service_kw", "deliveries_kg"):
                require(close(point[field], packet["forecast"][field][i]), f"Different {field}")
            action = point["action"]
            require(action["charge_kw"] * action["discharge_kw"] < 1e-6, "Simultaneous battery use")
            energy += (
                action["charge_kw"] * efficiency - action["discharge_kw"] / efficiency
            ) * packet["plant"]["dt_hours"]
            require(
                close(energy, point["state"]["battery_kwh"]), "Battery curve does not reconcile"
            )
        require(
            close(sum(p["action"]["methane_kg"] for p in points), totals["methane_kg"]),
            "Methane total differs",
        )
        require(points[-1]["state"] == totals["ending"], "Ending inventory differs")
        require(
            close(
                totals["assumed_value_eur"] - totals["variable_and_wear_eur"],
                totals["assumed_contribution_eur"],
            ),
            "Contribution differs",
        )
        require(
            prediction["solver"] == manifest["control_source"]["solver"][name],
            "Solver status differs",
        )
    checks.append(
        "Three saved policies share information; battery curves and displayed totals reconcile"
    )

    ledger = manifest["ledger"]
    require(
        [r["video_second"] for r in ledger] == list(range(STORY["duration"])),
        "Missing ledger seconds",
    )
    for entry in ledger:
        scene = next(s for s in STORY["scenes"] if s["start"] <= entry["video_second"] < s["end"])
        require(entry["scene"] == scene["id"], "Wrong scene")
        control = entry["control"]
        if control:
            hour = control["decision_hour"]
            require(
                entry["hour"] == hour + 1 and entry["fraction"] == 0,
                "Prediction advances physical plant",
            )
            view = fixture["views"][f"{entry['controller']}|{hour}"]
            require(view["hour"] == hour, "Wrong recorded decision")
            if control["comparison"]:
                require(
                    hour == packet["hour"] and control["information_id"] == identity,
                    "Wrong comparison context",
                )
        if any(a["asset"] == "human" and a["working"] for a in entry["actors"]):
            row = motion["props"]["value"]["records"][entry["controller"]][entry["hour"] - 1]
            require(
                row["applied"]["electrolyser_kw"] == 0, "Repair shown with powered electrolyser"
            )
    checks.append(
        "Every encoded second retains scene/context; active repair readouts show isolation"
    )

    probe = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(movie)]
        )
    )
    require(len(probe["streams"]) == 1, "Expected a single video stream and no audio")
    stream = probe["streams"][0]
    require(
        (stream["codec_name"], stream["pix_fmt"]) == ("h264", "yuv420p"), "Wrong video encoding"
    )
    require(
        (stream["width"], stream["height"]) == (STORY["width"], STORY["height"]), "Wrong resolution"
    )
    require(stream["avg_frame_rate"] == f"{STORY['fps']}/1", "Wrong frame rate")
    require(
        abs(float(probe["format"]["duration"]) - STORY["duration"]) <= 1 / STORY["fps"],
        "Wrong duration",
    )
    require(int(stream["nb_frames"]) == STORY["duration"] * STORY["fps"], "Missing frames")
    atoms = []
    with movie.open("rb") as file:
        while header := file.read(8):
            size, kind = struct.unpack(">I4s", header)
            header_size = 8
            if size == 1:
                size = struct.unpack(">Q", file.read(8))[0]
                header_size = 16
            atoms.append(kind.decode("ascii"))
            if size == 0:
                break
            require(size >= header_size, "Invalid MP4 atom")
            file.seek(size - header_size, 1)
    require(atoms.index("moov") < atoms.index("mdat"), "MP4 not prepared for streaming")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(movie), "-f", "null", "-"],
        check=True,
        capture_output=True,
    )
    checks.append("Full movie decodes: silent H.264, 1080p, 30 fps, 46 seconds, fast-start index")
    report = dict(
        schema="dispatch-demo-verification/1",
        movie=movie.name,
        sha256=sha(movie),
        bytes=movie.stat().st_size,
        checks=checks,
        scope="Presentation integrity only; no field or policy qualification",
    )
    Path(f"{BASE}-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
