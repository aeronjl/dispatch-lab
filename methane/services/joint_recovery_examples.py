"""Matched, reproducible operating examples of joint recovery and charging."""

import argparse
import base64
import html
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.evidence import save
from methane.offline_model import write as write_model_pages
from methane.provenance import LOADED_FILES, LOADED_SOURCE
from methane.recovery import JOINT_VERSION
from methane.reference import audit
from methane.service_economics import reprice_run
from methane.services.investigation_runs import write
from methane.services.verification_examples import CONTROLLER, weather_for
from methane.services.verification_examples import fixture as base_fixture
from methane.simulation import run

VERSION = "joint-recovery-operating-examples/1"
CASES = ("normal-independent", "normal-joint", "shortage-independent", "shortage-joint")


def fixture(case):
    if case not in CASES:
        raise ValueError("Unknown joint recovery example")
    c = base_fixture("successful-procedure")
    return replace(
        c,
        scenario=replace(c.scenario, hours=24, horizon_hours=6),
        field_operations=replace(c.field_operations, rover_enabled=True, reset_enabled=True),
        service_system=replace(c.service_system, inspector="mobile"),
        service_policy=replace(c.service_policy, robot_reserve_fraction=0.9, charging_wait_hours=3),
        recovery_policy=replace(
            c.recovery_policy,
            version=JOINT_VERSION if case.endswith("-joint") else "scheduled-load-tests/1",
        ),
    )


def evaluate(case):
    c = fixture(case)
    result = run(
        c,
        weather=weather_for(
            c, "power-shortage" if case.startswith("shortage-") else "successful-procedure"
        ),
        strategies=[CONTROLLER],
    )
    rows = result["records"][CONTROLLER]
    costs = reprice_run(result, c.service_economics)["controllers"][CONTROLLER]
    summary = dict(
        version=VERSION,
        case=case,
        run_id=result["run_id"],
        source=LOADED_SOURCE["content_hash"],
        status=result["status"],
        failures=result["failures"],
        metrics=result["metrics"][CONTROLLER],
        costs={k: v for k, v in costs.items() if k != "services"},
        service_costs={
            k: v for k, v in costs["services"].items() if k in ("views", "quantities", "basis")
        },
        ending_plant=rows[-1]["state"] if rows else None,
        ending_estimate=rows[-1]["diagnosis_after"] if rows else None,
        ending_services=rows[-1]["field_operations"]["state"] if rows else None,
        timeline=[
            dict(
                hour=r["hour"],
                requested_kw=r["requested"]["electrolyser_kw"],
                applied_kw=r["applied"]["electrolyser_kw"],
                dock_input_kwh=r["field_operations"].get("charge_input_kwh", 0),
                estimated_capacity_kw=r["diagnosis_after"]["capacity_kw"],
                recovery={
                    k: v
                    for k, v in r["decision"]["recovery_planning"].items()
                    if k not in ("plan", "candidate_windows")
                },
                service_status=r["decision"]["service_control"]["status"],
            )
            for r in rows
        ],
        independent_check=audit(result),
        boundary="24 realised hourly intervals, seed 7, six-hour forecast. Ending inventories and unverified health remain reported; no later repair or sale proceeds are inferred. Procedure reliability and weather are illustrative, not calibrated.",
    )
    return result, summary


def render(summaries):
    e = html.escape
    font = base64.b64encode(LOADED_FILES["assets/fonts/DepartureMono-Regular.woff2"]).decode()
    body = []
    for s in summaries:
        m = s["metrics"]
        facts = dict(
            status=s["status"],
            methane_kg=m["methane_kg"],
            allocated_eur=s["costs"]["allocated_eur"],
            assumed_contribution_eur=s["costs"]["assumed_contribution_eur"],
            ending_estimate_kw=s["ending_estimate"]["capacity_kw"]
            if s["ending_estimate"]
            else None,
            confirmation_delay_hours=m["recovery_confirmation_delay_hours"],
            deadline_misses=m["recovery_deadline_misses"],
            independent_checks_passed=s["independent_check"]["passed"],
        )
        body.append(
            f'<article id="{e(s["case"])}"><h2>{e(s["case"].replace("-", " "))}</h2><dl>'
            + "".join(
                f"<dt>{e(k.replace('_', ' '))}</dt><dd>{e(str(round(v, 3) if isinstance(v, float) else v))}</dd>"
                for k, v in facts.items()
            )
            + "</dl>"
        )
        body.append(
            '<div class="scroll" tabindex="0" role="region" aria-label="Recorded test and charging timeline"><table><thead><tr><th>Hour</th><th>Request / delivery, kW</th><th>Dock input, kWh</th><th>Recovery scheduling</th></tr></thead><tbody>'
        )
        for r in s["timeline"]:
            recovery = r["recovery"]
            body.append(
                f"<tr><td>{r['hour']}</td><td>{r['requested_kw']:.2f} / {r['applied_kw']:.2f}</td><td>{r['dock_input_kwh']:.3f}</td><td>{e(recovery['status'])}"
                + (
                    f" · accepted H{recovery['commitment']['start_hour']}–H{recovery['commitment']['end_hour']}, due H{recovery['commitment']['due_hour']}"
                    if recovery.get("commitment")
                    else ""
                )
                + "</td></tr>"
            )
        body.append(
            f'</tbody></table></div><p>{e(s["boundary"])}</p><p><a href="{s["case"]}/playback.html">Recorded operation</a> · <a href="{s["case"]}/summary.json">Full outcomes, assumptions and ending inventories</a> · <a href="{s["case"]}/model-report.html">Original model explanation</a> · <a href="{s["case"]}/reproduction.zip">Reproduction bundle</a></p></article>'
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Recovery tests share the electricity budget</title><style>@font-face{font-family:Departure;src:url(data:font/woff2;base64,'
        + font
        + ")}*{box-sizing:border-box}body{margin:0;background:#222;color:#ffa52b;font:14px/1.7 Departure,monospace;overflow-wrap:anywhere}main{max-width:1050px;margin:auto;padding:4vw}h1{font-size:26px}h2{font-size:19px}a{color:inherit}article{border-top:1px solid #88591c;margin-top:3rem;padding-top:2rem}dl{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:.4rem}dd{margin:0}.scroll{overflow:auto}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:.5rem;border-bottom:1px solid #88591c;white-space:nowrap}:focus-visible{outline:2px solid #ffd591}@media(max-width:600px){body{font-size:12px}main{padding:18px}}</style><main><p>Dispatch Lab · reproducible operating examples</p><h1>Recovery tests share the electricity budget</h1><p>Four 24-hour runs compare independent test scheduling with joint service, charging and test planning. Within each matched pair, only the recovery policy version changes. The plant, sensor streams, mobile inspector, 90% robot reserve target, three-hour charging deadline, service resources and prices are identical. A second pair removes power from H14. Both retain persistent faults and actual post-service observations.</p><p>A joint plan retains an accepted test window until measured progress consumes it or an explicitly recorded interruption releases it. Failed tracking and new procedure receipts do not move the original deadline. The controller sees no private repair outcome. A test can remain infeasible; useful service fallback and unconfirmed health remain visible.</p><p>These short fixtures test coordination, not general controller superiority, annual economics or calibrated fault probabilities. A higher methane total can coexist with delayed maintenance or a lower ending inventory. Read the timeline and ending state with the aggregate totals. The independent arm uses the older rolling window semantics; this is a declared policy-package comparison, not an isolated optimiser ablation.</p>"
        + "".join(body)
        + f"<p>Source {e(LOADED_SOURCE['content_hash'])}. All incomplete and failed outcomes are retained. Offline playback reads saved records; numerical reruns require the restored application and may differ under finite solver limits.</p></main></html>"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("build/services/joint-recovery/recorded") / LOADED_SOURCE["content_hash"],
    )
    args = parser.parse_args()
    if args.directory.exists() and any(args.directory.iterdir()):
        parser.error("Choose an empty directory; previous evidence is immutable")
    args.directory.mkdir(parents=True, exist_ok=True)
    summaries = []
    for case in CASES:
        result, summary = evaluate(case)
        dest = args.directory / case
        archive = save(result, dest)
        summary["archive"] = archive.name
        write(dest / "summary.json", json.dumps(summary, indent=2, allow_nan=False) + "\n")
        write(dest / "playback.html", playback(result, LOADED_FILES))
        write_model_pages(result, dest, archive_href=archive.name)
        make(result, dest / "reproduction.zip")
        summaries.append(summary)
        print(
            case,
            result["status"],
            "independent checks",
            summary["independent_check"]["passed"],
            flush=True,
        )
    write(
        args.directory / "manifest.json",
        json.dumps(
            dict(
                version=VERSION,
                source=LOADED_SOURCE["content_hash"],
                cases=[
                    dict(case=s["case"], run_id=s["run_id"], status=s["status"]) for s in summaries
                ],
            ),
            indent=2,
        )
        + "\n",
    )
    write(args.directory / "report.html", render(summaries))


if __name__ == "__main__":
    main()
