"""Offline reference replay and explicit source reconstruction; never fetch implicitly."""

import argparse
import json
from pathlib import Path

import numpy as np

from methane.literature.adapters import rebuild
from methane.literature.service import PROFILES, calculate, profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "verify-sources"))
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--inputs", type=Path, help="JSON request; profile must match")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        inputs = json.loads(args.inputs.read_text()) if args.inputs else {"profile": args.profile}
        if inputs.get("profile") != args.profile:
            parser.error("Input profile differs from selected adapter")
        result = calculate(inputs)
    else:
        if args.directory is None:
            parser.error("verify-sources needs --directory containing all declared original files")
        p = profile(args.profile)
        rebuilt = rebuild(p, args.directory)
        if len(rebuilt["rows"]) != len(p["data"]["rows"]):
            raise ValueError("Rebuilt row count differs from the frozen dataset")
        for actual, expected in zip(rebuilt["rows"], p["data"]["rows"], strict=True):
            for k, v in expected.items():
                if isinstance(v, float):
                    if not np.isclose(actual[k], v, rtol=1e-12, atol=1e-12):
                        raise ValueError("Rebuilt observations differ: " + k)
                elif actual[k] != v:
                    raise ValueError("Rebuilt selection differs: " + k)
        result = dict(
            status="Original byte identities and reconstructed observations match",
            profile=args.profile,
            rows=len(rebuilt["rows"]),
        )
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
