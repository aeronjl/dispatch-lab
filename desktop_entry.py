"""Private interpreter entry point; bootstrap paths before importing the app."""

import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Dispatch Lab desktop runtime")
    parser.add_argument("mode", choices=["serve", "mcp", "check"])
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    from methane.paths import bootstrap

    bootstrap(args.workspace)
    root = Path(__file__).resolve().parent
    if (root / "dispatch-release.json").exists():
        from methane.desktop_host import verify_release

        verify_release(root)
    elif os.environ.get("DISPATCH_DESKTOP_DEVELOPMENT") != "1":
        raise ValueError("Installed source manifest is missing")
    if args.mode == "mcp":
        from methane.mcp_server import server

        server.run(transport="stdio")
    elif args.mode == "check":
        from methane.desktop_check import check

        check()
    else:
        import app

        app.main(
            ["--port", str(args.port)] + (["--archive", str(args.archive)] if args.archive else []),
            desktop=True,
        )


if __name__ == "__main__":
    main()
