"""Saved service-event matching fixtures, with original-source reproduction bundles."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.evidence import save
from methane.provenance import LOADED_FILES, LOADED_SOURCE
from methane.reference import audit
from methane.services.hardware_demo import fixture as hardware_fixture
from methane.services.randomness import VERSION
from methane.services.visits_demo import execute
from methane.services.visits_demo import fixture as visit_fixture

CASES = ("crew-repair", "cleaner-retrieval", "hardware-replacement")
FIXTURE = "service-event-matching-examples/1"


def fixture(name):
    if name not in CASES:
        raise ValueError("Unknown service-event example")
    if name == "crew-repair":
        c = visit_fixture("interventions")
        c = replace(c, field_operations=replace(c.field_operations, repair_success_probability=0.5))
    elif name == "cleaner-retrieval":
        c = hardware_fixture("control-hold")
        c = replace(
            c,
            field_operations=replace(c.field_operations, mission_failure_probability=1),
            service_system=replace(c.service_system, equipment_recovery_enabled=False),
        )
    else:
        c = hardware_fixture("drive-power-loss")
        c = replace(c, field_operations=replace(c.field_operations, repair_success_probability=0.8))
    return replace(c, service_system=replace(c.service_system, outcome_randomness=VERSION))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/matching"))
    base = parser.parse_args().directory
    base.mkdir(parents=True, exist_ok=True)
    summary = []
    lines = [
        "# Matching an event is separate from predicting its outcome",
        "",
        "Three saved, seeded constant-irradiance fixtures exercise accepted crew jobs, partial cleaning followed by retrieval, and failed service hardware. They use Greedy production and the existing local service rule. Event matching does not introduce a joint planner or empirically calibrated reliability. Every probability, configuration, private draw and unresolved job is preserved in the archive.",
        "",
        "| Example | Private draws | Methane kg | Independent checks |",
        "|---|---:|---:|---|",
    ]
    for name in CASES:
        result = execute(fixture(name))
        checked = audit(result)
        archive = save(result, base)
        make(result, base / (name + "-reproduction.zip"))
        (base / (name + "-playback.html")).write_text(playback(result, LOADED_FILES))
        (base / (name + "-audit.json")).write_text(json.dumps(checked, indent=2) + "\n")
        rows = result["records"]["Greedy"]
        draws = [
            d
            for r in result["retrospective_truth_by_controller"]["Greedy"]
            for d in r["service_randomness"]
        ]
        item = dict(
            fixture_id=FIXTURE,
            case=name,
            source=LOADED_SOURCE["content_hash"],
            run_id=result["run_id"],
            archive=archive.name,
            status=result["status"],
            failures=result["failures"],
            audit_passed=checked["passed"],
            independent_checks=len(checked["checks"]),
            draws=draws,
            methane_kg=sum(r["applied"]["methane_kg"] for r in rows),
            ending_plant=rows[-1]["state"] if rows else None,
            ending_services=rows[-1]["field_operations"]["state"] if rows else None,
        )
        summary.append(item)
        lines.append(
            f"| [{name}]({name}-playback.html) | {len(draws)} | {item['methane_kg']:.3f} | {'Passed' if checked['passed'] else 'Failed'}: {item['independent_checks']} |"
        )
        print(
            json.dumps(
                {
                    k: item[k]
                    for k in ("case", "status", "run_id", "audit_passed", "independent_checks")
                }
            ),
            flush=True,
        )
    lines += [
        "",
        "The outcome ledger is explicitly retrospective. Request identities are public, but their realised variates are not controller evidence. A completed procedure does not establish recovery; the later operating test and its observations remain separate. Repair success, repair applicability and post-service acceptance can therefore differ.",
        "",
        "Changing reason text, actor or schedule leaves a matching target/action/request draw unchanged. Changing the procedure, number of accepted attempts or probability can change the outcome. Rejected candidates consume no request number; cancelled accepted work keeps its number. Referenced contact-reader noise uses its own model.",
        "",
        "Each reproduction bundle contains the original source, recorded run, self-contained playback, Model report and standard-library checker. Numerical rerun differences must be inspected separately from recorded playback. Existing studies continue to use their originally frozen mapping.",
    ]
    (base / "cases.json").write_text(json.dumps(summary, indent=2) + "\n")
    (base / "report.md").write_text("\n".join(lines) + "\n")
    print(base / "report.md", flush=True)
    if not all(x["status"] == "complete" and x["audit_passed"] for x in summary):
        raise SystemExit("A service-event example is incomplete or failed independent checks")


if __name__ == "__main__":
    main()
