"""Recorded operating examples for measured post-service follow-up.

These are bounded workflow comparisons, not calibrated maintenance economics.
"""

import argparse
import base64
import html
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.config import Costs
from methane.evidence import publish_completed, save, staging
from methane.offline_model import write as write_model_pages
from methane.provenance import LOADED_FILES, LOADED_SOURCE
from methane.recovery import RecoveryPolicy
from methane.reference import audit
from methane.service_economics import ACTIVITY_VERSION, illustrative, reprice_run
from methane.services.controller import VERIFICATION_VERSION, ServicePolicy
from methane.services.inspection_demo import fixture as base_fixture
from methane.simulation import run
from methane.weather import synthetic

VERSION = "post-service-execution-examples/1"
CASES = ("failed-procedure", "single-attempt-baseline", "successful-procedure", "power-shortage")
CONTROLLER = "MPC · methane"


def fixture(case="failed-procedure"):
    if case not in CASES:
        raise ValueError("Unknown post-service example")
    c = base_fixture()
    return replace(
        c,
        scenario=replace(c.scenario, hours=40, horizon_hours=6, solver_seconds=0.15),
        field_operations=replace(
            c.field_operations,
            reset_enabled=False,
            rover_enabled=False,
            repair_success_probability=1 if case == "successful-procedure" else 0,
            service_kits=3,
        ),
        service_system=replace(
            c.service_system,
            inspector="none",
            support_model="logistics/1",
            crew_response_lead_hours=0,
            crew_travel_hours=0.25,
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
            visit_bundling_enabled=True,
            outcome_randomness="target-action-request/1",
        ),
        service_economics=illustrative(Costs(), version=ACTIVITY_VERSION),
        recovery_policy=RecoveryPolicy(retry_after_hours=1, maximum_wait_hours=6),
        service_policy=ServicePolicy(
            version="coordinated-services/2"
            if case == "single-attempt-baseline"
            else VERIFICATION_VERSION,
            maximum_wait_hours=8,
            maximum_candidates=4,
            comparison_seconds=0.5,
        ),
    )


def weather_for(c, case):
    weather = synthetic(c)
    for mapping in (weather["truth"], weather["template"]):
        for i, sample in enumerate(mapping.values()):
            power = 0 if case == "power-shortage" and i >= 14 else 750
            sample.update(pv_kw=power, irradiance_wm2=power, ambient_c=20)
    weather["reference"] = (
        "Illustrative 750 kW hourly mean DC and 20°C workflow fixture; power-shortage case supplies zero from H14. Not measured weather."
    )
    return weather


def evaluate(case):
    c = fixture(case)
    result = run(c, weather=weather_for(c, case), strategies=[CONTROLLER])
    checked = audit(result)
    rows = result["records"][CONTROLLER]
    costs = reprice_run(result, c.service_economics)["controllers"][CONTROLLER]
    summary = dict(
        case=case,
        schema_version=VERSION,
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
        last_decision_obligations=rows[-1]["decision"]["service_control"]["obligations"]
        if rows
        else [],
        verification=rows[-1]["decision"]["service_control"].get("verification") if rows else None,
        independent_check=checked,
        boundary="Service obligations use the last decision boundary; final-interval plant/service inventories are shown separately. No later verification is inferred.",
    )
    return result, summary


def write(path, value):
    with staging(path) as temporary:
        temporary.write_text(value)
        return publish_completed(temporary, path)


def render(summaries):
    esc = html.escape
    font = base64.b64encode(LOADED_FILES["assets/fonts/DepartureMono-Regular.woff2"]).decode()
    body = []
    for s in summaries:
        m, c, v = s["metrics"], s["costs"], s["verification"]
        attempts = [] if v is None else v["attempts"]
        facts = dict(
            status=s["status"],
            methane_kg=m["methane_kg"],
            allocated_eur=c["allocated_eur"],
            decision_cost_eur=c["decision_cost_eur"],
            assumed_contribution_eur=c["assumed_contribution_eur"],
            estimated_capacity_kw=s["ending_estimate"]["capacity_kw"]
            if s["ending_estimate"]
            else None,
            unresolved_obligations=m["service_control"]["unresolved_obligations"],
            repair_retries=m["service_control"]["repair_retries"],
            fallback_intervals=m["service_control"]["fallback_intervals"],
        )
        body.append(
            f'<article id="{esc(s["case"])}"><h2>{esc(s["case"].replace("-", " "))}</h2><dl>'
            + "".join(
                f"<dt>{esc(k.replace('_', ' '))}</dt><dd>{esc(str(round(x, 3) if isinstance(x, float) else x))}</dd>"
                for k, x in facts.items()
            )
            + "</dl>"
        )
        for a in attempts:
            body.append(
                f"<p>{esc(a['order_id'])}: {esc(a['status'])}. Whole mission completed at boundary H{a['completed_at']}. "
                + esc(a.get("reason", ""))
                + '</p><div class="scroll" tabindex="0" role="region" aria-label="Recorded post-service tests"><table><thead><tr><th>Interval</th><th>Requested / kW</th><th>Observed test</th></tr></thead><tbody>'
                + "".join(
                    f"<tr><td>H{t['hour']} → H{t['available_at']}</td><td>{t['requested_kw']:.2f}</td><td>{esc(t['outcome'])}</td></tr>"
                    for t in a["tests"]
                )
                + "</tbody></table></div>"
            )
        if v is None:
            body.append(
                "<p>The baseline does not run the new follow-up rule. Its unverified work remains in the original trace; no missing test record is reconstructed.</p>"
            )
        body.append(
            f'<p>{esc(s["boundary"])}</p><p><a href="{s["case"]}/playback.html">Recorded operation</a> · <a href="{s["case"]}/model-report.html">Original model documentation</a> · <a href="{s["case"]}/summary.json">Full outcomes and ending inventories</a> · <a href="{s["case"]}/reproduction.zip">Source and reproduction bundle</a></p></article>'
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>After the repair: operating verification</title><style>@font-face{font-family:Departure;src:url(data:font/woff2;base64,'
        + font
        + ')}*{box-sizing:border-box}body{background:#222;color:#ffa52b;font:14px/1.7 Departure,monospace;margin:0;overflow-wrap:anywhere}main{max-width:1000px;margin:auto;padding:4vw}h1{font-size:26px}h2{font-size:19px}a{color:inherit}article{border-top:1px solid #88591c;margin-top:3rem;padding-top:2rem}dl{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:.35rem 1rem}dd{margin:0}dt{color:#d3933d}.scroll{overflow:auto}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:.5rem;border-bottom:1px solid #88591c;white-space:nowrap}:focus-visible{outline:2px solid #ffd591;outline-offset:4px}@media(max-width:600px){body{font-size:12px}main{padding:18px}h1{font-size:22px}}</style><main><p>Dispatch Lab · recorded operating examples</p><h1>What happens after a repair fails its tests?</h1><p>Four 40-hour examples retain the same plant and a persistent capacity loss injected at H2. The two failed-procedure arms differ only in service-policy version. A successful-procedure sensitivity changes the declared intervention reliability from zero to one. The shortage sensitivity removes power from H14. Reliability is an illustrative challenge setting, not an empirical probability.</p><p>The controller receives actual sensor observations and public service receipts. It never receives the injected cause or private repair result. A completed substitution stays unverified until operating evidence supports recovery. Version 3 can make a separate bounded attempt after repeated resource-feasible load-test shortfalls; its original work deadline and attempt limit do not move.</p><p>Repeated repair can be costly without restoring production. These examples test follow-through and accounting, not superiority of robotics or a calibrated maintenance strategy. They do not implement the separate inspect-first contingency planner, posterior transitions after repair, or jointly reserved future test and charging schedules.</p><nav aria-label="Examples">'
        + " · ".join(
            f'<a href="#{s["case"]}">{esc(s["case"].replace("-", " "))}</a>' for s in summaries
        )
        + "</nav>"
        + "".join(body)
        + f"<p>Source {esc(LOADED_SOURCE['content_hash'])}. Reproduction reuses saved inputs and captured source; finite solver searches may differ. All incomplete and failed outcomes remain recorded. Offline playback does not rerun numerical work.</p></main></html>"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("build/services/verification/recorded") / LOADED_SOURCE["content_hash"],
    )
    args = parser.parse_args()
    if args.directory.exists() and any(args.directory.iterdir()):
        parser.error(
            "This output directory already contains evidence; choose a new --directory for another execution"
        )
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
    report = write(args.directory / "report.html", render(summaries))
    write(
        args.directory / "manifest.json",
        json.dumps(
            dict(
                schema_version=VERSION,
                source=LOADED_SOURCE["content_hash"],
                cases=[
                    dict(
                        case=s["case"],
                        archive=s["archive"],
                        run_id=s["run_id"],
                        passed=s["independent_check"]["passed"],
                    )
                    for s in summaries
                ],
            ),
            indent=2,
        )
        + "\n",
    )
    print(report)
    if not all(s["independent_check"]["passed"] for s in summaries):
        raise SystemExit("An operating example failed independent accounting checks")


if __name__ == "__main__":
    main()
