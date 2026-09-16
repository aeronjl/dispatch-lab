"""Isolated original-information comparison; receives no completed source run."""

import json
import os
import sys
from pathlib import Path


def main():
    root = Path(sys.argv[1])
    try:
        os.nice(5)
    except (AttributeError, OSError):
        pass

    def progress(message):
        (root / "progress.txt").write_text(message)

    progress("Loading recorded decision information")
    from methane.control_view import compare, compare_alternative

    try:
        inputs = json.loads((root / "input.json").read_text())
        result = (compare_alternative if inputs.get("alternative") else compare)(
            inputs, progress=progress
        )
    except (ValueError, KeyError, TypeError) as exc:
        result = dict(status="incomplete", error=str(exc))
    # Pollers only read a complete file, including while the worker exits.
    pending = root / "result.pending"
    pending.write_text(json.dumps(result, allow_nan=False))
    pending.replace(root / "result.json")


if __name__ == "__main__":
    main()
