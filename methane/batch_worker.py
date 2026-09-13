"""One low-priority batch process; parent cancellation is checked between solves."""

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass
    from methane.config import Config
    from methane.simulation import run

    request = json.loads((root / "input.json").read_text())

    def progress(fraction, desc=""):
        temporary = root / "progress.tmp"
        temporary.write_text(json.dumps({"fraction": fraction, "description": desc}))
        temporary.replace(root / "progress.json")

    try:
        result = run(
            Config.from_dict(request["config"]),
            weather=request["weather"],
            strategies=request.get("strategies"),
            cancelled=lambda: (root / "cancel").exists(),
            progress=progress,
        )
        (root / "result.json").write_text(json.dumps(result, allow_nan=False))
    except Exception as exc:
        (root / "error.json").write_text(
            json.dumps({"type": type(exc).__name__, "message": str(exc)})
        )
        raise


if __name__ == "__main__":
    main()
