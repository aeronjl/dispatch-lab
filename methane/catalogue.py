"""Generated component contracts and source-bound evidence, suitable for CI freshness gates."""

import argparse
import hashlib
import json
import platform
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from methane.battery import BatteryState
from methane.components import assemble
from methane.config import Config, Models
from methane.contracts import SPECS
from methane.electrolyser import State as ElyState
from methane.provenance import LOADED_SOURCE, digest
from methane.reactor import ReactorState
from methane.storage import State as GasState

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "docs/component-catalogue.json"


def catalogue():
    c = Config()
    components = assemble(c.plant)
    blocks = {
        "battery": components.battery.planning(BatteryState(0), (1,)),
        "electrolyser": components.electrolyser.planning(ElyState(), 450, (1,)),
        "hydrogen": components.hydrogen.planning(GasState(0), 1),
        "co2": components.co2.planning(GasState(500), 1, (0,)),
        "reactor": components.reactor.planning(ReactorState(20), (20,), (1,)),
    }
    entries = {}
    for key, spec in SPECS.items():
        entry = spec.to_dict()
        entry["spec_sha256"] = digest(entry)
        if key in blocks:
            entry["planning_ports"] = [asdict(p) for p in blocks[key].ports]
            entry["planning_constraints"] = sorted({r.name for r in blocks[key].rows})
        entries[key] = entry
    from methane.model_topics import TOPICS

    return dict(
        documentation_topics={
            k: {"title": t["title"], "version": t["version"], "fixture_id": t["fixture_id"]}
            for k, t in TOPICS.items()
        },
        schema_version="dispatch-lab/component-catalogue/1",
        components=entries,
        default_implementations=asdict(Models()),
        result_schemas={
            "methane": ["dispatch-lab/methane/2", "dispatch-lab/methane/3"],
            "battery": "dispatch-lab/battery-record/1",
            "component": "dispatch-lab/component-record/1",
            "source": "dispatch-lab/source-capsule/1",
            "bundle": "dispatch-lab/reproduction-bundle/1",
        },
        compatibility="Schema 2/3 meanings remain unchanged; additive records are unavailable on older archives, never reconstructed as original evidence.",
        boundary="Pure kernels depend only on contracts/audits/portable rows/time helpers. Plant assembly owns bus allocation and observation-versus-truth context.",
    )


def write(check_only=False):
    expected = json.dumps(catalogue(), indent=2, sort_keys=True, allow_nan=False) + "\n"
    if check_only:
        if not CATALOGUE.exists() or CATALOGUE.read_text() != expected:
            raise ValueError(
                "Generated component catalogue is stale. Run python -m methane.catalogue generate."
            )
    else:
        CATALOGUE.write_text(expected)


def stamp(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "source-under-test.json").write_text(
        json.dumps(
            {
                "source": LOADED_SOURCE,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            indent=2,
        )
    )


def evidence(directory):
    directory = Path(directory)
    bound = json.loads((directory / "source-under-test.json").read_text())
    matches = bound["source"]["content_hash"] == LOADED_SOURCE["content_hash"]
    checks = []
    xml = directory / "pytest.xml"
    if xml.exists():
        suites = ET.parse(xml).getroot()
        suites = list(suites) if suites.tag == "testsuites" else [suites]
        failed = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
        count = sum(int(s.get("tests", 0)) for s in suites)
        checks.append(
            dict(name="python", passed=not failed and count > 0, tests=count, failures=failed)
        )
    for filename in (
        "mutations.json",
        "browser-tests.json",
        "browser-recorded.json",
        "browser-active.json",
        "formal.json",
        "performance-gates.json",
        "offline-check.json",
        "recomputation.json",
    ):
        path = directory / filename
        if not path.exists():
            checks.append(dict(name=filename, status="not-run"))
            continue
        value = json.loads(path.read_text())
        if filename == "mutations.json":
            passed = bool(value) and all(v["detected"] for v in value)
        elif filename in ("browser-tests.json", "browser-recorded.json"):
            passed = (
                value.get("stats", {}).get("unexpected", 1) == 0
                and value.get("stats", {}).get("expected", 0) > 0
            )
        elif filename == "browser-active.json":
            passed = (
                value["batch_active"]
                and value["fixture_hours"] >= 240
                and value["preview_p95_ms"] <= 200
                and value["render_p95_ms"] <= 10
            )
        elif filename == "formal.json":
            passed = len(value["cases"]) == 4 and all(c["passed"] for c in value["cases"])
        elif filename == "performance-gates.json":
            passed = value["passed"]
        elif filename == "offline-check.json":
            passed = value["status"] == "passed"
        else:
            passed = value["independent_reference_passed"] and value["source_matches"]
        checks.append(
            dict(name=filename, passed=passed, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        )
    report = dict(
        schema_version="dispatch-lab/evidence-catalogue/1",
        source=bound["source"],
        source_still_matches=matches,
        component_catalogue_sha256=digest(catalogue()),
        checks=checks,
        passed=matches and bool(checks) and all(c.get("passed", False) for c in checks),
        scope="These artifacts belong to the source stamped before validation. Missing, failed and incomplete evidence remains visible; older reports are not silently promoted.",
    )
    (directory / "evidence-catalogue.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("generate", "check", "stamp", "evidence"))
    p.add_argument("--directory", type=Path, default=ROOT / "build/engineering/current")
    args = p.parse_args()
    if args.command in ("generate", "check"):
        write(args.command == "check")
    elif args.command == "stamp":
        stamp(args.directory)
    else:
        report = evidence(args.directory)
        print(json.dumps(report, indent=2))
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
