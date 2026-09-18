"""Verify the film's source identities, recorded mechanisms and delivery format."""

import argparse
import gzip
import hashlib
import json
import math
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/submission-video"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(gzip.decompress((ROOT / path).read_bytes()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(
        (OUT / ("preview-manifest.json" if args.preview else "manifest.json")).read_text()
    )
    story, ledger = manifest["story"], manifest["ledger"]
    checks = []
    require(60 <= story["duration"] <= 300, "Film must last 1–5 minutes")
    require(not manifest["errors"] and not manifest["network"], "Browser errors or network fetches")
    for name, expected in manifest["sourceHashes"].items():
        require(sha(ROOT / name) == expected, f"Render source changed: {name}")
    sources = {}
    for name, source in manifest["sources"].items():
        for item in source.values():
            require(sha(ROOT / item["path"]) == item["sha256"], f"Changed fixture: {name}")
        motion, control = read(source["motion"]["path"]), read(source["control"]["path"])
        require(motion["source_run_id"] == control["source_run_id"], "Run context mismatch")
        require(
            motion["source_integrity"] == control["source_integrity"], "Archive context mismatch"
        )
        sources[name] = (motion, control)
    for shot in manifest["capture"]["shots"]:
        require(sha(ROOT / shot["file"]) == shot["sha256"], "UI screenshot changed")
    checks.append("Offline render, saved UI captures, implementation and fixture hashes match")
    require(
        sources["operation"][0]["source_run_id"] != sources["recovery"][0]["source_run_id"],
        "Expected separate examples",
    )
    recovery_card = next(s for s in story["scenes"] if s["id"] == "verify-card")
    require("separate" in recovery_card["subtitle"], "Separate recovery context must be disclosed")
    checks.append(
        "Design exploration, operating archive and controlled recovery are separate contexts"
    )

    comparison = sources["operation"][1]
    packet, result = comparison["input_packet"], comparison["comparison"]
    identity = hashlib.sha256(
        json.dumps(
            {k: v for k, v in packet.items() if k != "information_id"},
            sort_keys=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    require(
        identity == packet["information_id"] == result["information_id"],
        "Comparison information mismatch",
    )
    require(packet["state"] == result["initial"], "Comparison initial state differs")
    require(packet["cost_version"] == result["cost_version"], "Comparison costs differ")
    require(len(result["predictions"]) == 3, "Three policies required")
    for name, prediction in result["predictions"].items():
        require(prediction["information_id"] == identity, f"Different inputs for {name}")
        energy = packet["state"]["battery_kwh"]
        efficiency = math.sqrt(packet["plant"]["roundtrip_efficiency"])
        for point in prediction["points"]:
            action = point["action"]
            energy += (
                action["charge_kw"] * efficiency - action["discharge_kw"] / efficiency
            ) * packet["plant"]["dt_hours"]
            require(
                math.isclose(energy, point["state"]["battery_kwh"], abs_tol=1e-6),
                "Battery trajectory does not reconcile",
            )
        require(
            math.isclose(
                sum(p["action"]["methane_kg"] for p in prediction["points"]),
                prediction["predicted"]["methane_kg"],
                abs_tol=1e-6,
            ),
            "Predicted production does not reconcile",
        )
        require(prediction["solver"]["status"], "Missing solver limitation")
    checks.append(
        "Three predicted policies share original information; displayed battery and production totals reconcile"
    )

    recovery = sources["recovery"][0]["props"]["value"]
    rows = recovery["records"][story["controller"]]
    require(
        recovery["config"]["recovery_policy"]["version"] == "scheduled-load-tests/5",
        "Wrong recovery mechanism",
    )
    require(
        rows[14]["diagnosis_after"]["capacity_kw"] == 225,
        "Repair receipt improperly equated with full recovery",
    )
    for h, capacity in [(16, 270), (18, 315), (20, 360), (22, 405), (24, 450)]:
        require(
            rows[h]["diagnosis_after"]["capacity_kw"] == capacity,
            "Observed capacity sequence changed",
        )
        require(
            rows[h]["diagnosis_after"]["informative"], "Confirmation lacks informative tracking"
        )
    checks.append(
        "Repair remains unverified at H15; five observed confirmations restore capacity through H25"
    )
    for entry in ledger:
        scene = next(s for s in story["scenes"] if s["start"] <= entry["second"] < s["end"])
        require(entry["id"] == scene["id"], "Scene timing mismatch")
        if "recorded" not in entry:
            continue
        recorded = entry["recorded"]
        require(recorded["hour"] == math.floor(recorded["at"] + 1e-8), "Playhead mismatch")
        motion, controls = sources[scene["kind"]]
        row = motion["props"]["value"]["records"][recorded["controller"]][
            max(0, recorded["hour"] - 1)
        ]
        if recorded["control"]:
            require(recorded["fraction"] == 0, "Prediction advanced physical playback")
            key = f"{recorded['controller']}|{recorded['hour'] - 1}"
            require(key in controls["views"], "Missing recorded decision")
        for actor in recorded["actors"]:
            require(
                math.isfinite(actor["x"]) and math.isfinite(actor["y"]), "Invalid sprite position"
            )
            if actor["asset"] == "human" and actor["working"]:
                require(
                    row["applied"]["electrolyser_kw"] == 0, "Repair shown with powered electrolyser"
                )
    checks.append(
        "Recorded playheads, prediction separation, sprite positions and repair isolation reconcile"
    )

    if not args.preview:
        require(
            [r["second"] for r in ledger] == list(range(story["duration"])),
            "Missing per-second ledger",
        )
        movie = OUT / (story["output"] + ".mp4")
        probe = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(movie),
                ]
            )
        )
        require(len(probe["streams"]) == 1, "Expected video only, no audio")
        stream = probe["streams"][0]
        require(
            (stream["codec_name"], stream["pix_fmt"], stream["width"], stream["height"])
            == ("h264", "yuv420p", 1920, 1080),
            "Unexpected encoding",
        )
        require(stream["avg_frame_rate"] == "30/1", "Unexpected frame rate")
        require(
            abs(float(probe["format"]["duration"]) - story["duration"]) < 1 / 30, "Wrong duration"
        )
        require(int(stream["nb_frames"]) == 30 * story["duration"], "Missing encoded frames")
        atoms = []
        with movie.open("rb") as file:
            while header := file.read(8):
                size, kind = struct.unpack(">I4s", header)
                if size == 1:
                    size = struct.unpack(">Q", file.read(8))[0]
                    skip = size - 16
                else:
                    skip = size - 8
                require(size > 0, "Unbounded atom")
                atoms.append(kind.decode())
                file.seek(skip, 1)
        require(atoms.index("moov") < atoms.index("mdat"), "MP4 is not fast-start")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-xerror", "-i", str(movie), "-f", "null", "-"], check=True
        )
        checks.append(
            "168 seconds, 5040 frames, 1080p30 H.264, no audio, fast-start and complete decode"
        )
    report = {
        "passed": True,
        "scope": "Presentation integrity and recorded numerical operands; not new policy qualification or field validation",
        "checks": checks,
        "limitations": manifest["limitations"],
    }
    (OUT / ("preview-verification.json" if args.preview else "verification.json")).write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
