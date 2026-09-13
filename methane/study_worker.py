"""Run one study edition with the source frozen at creation."""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass
    from methane.studies import atomic, run_edition

    directory = args.directory.resolve()
    try:
        run_edition(directory.name, directory.parent, args.fresh)
    except Exception as exc:
        atomic(
            directory / "progress.json",
            {"status": "failed", "description": f"{type(exc).__name__}: {exc}"},
        )
        raise


if __name__ == "__main__":
    main()
