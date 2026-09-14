"""Process entry point for expensive, isolated learning calculations."""

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
    (root / "progress.txt").write_text("Calculating the shared fixture with bounded solver calls")
    from methane.learning import evaluate, progress_callback

    progress_callback.set(lambda message: (root / "progress.txt").write_text(message))

    args = json.loads((root / "input.json").read_text())
    answer = evaluate(args["topic"], args["inputs"])
    (root / "result.json").write_text(json.dumps(answer, allow_nan=False))


if __name__ == "__main__":
    main()
