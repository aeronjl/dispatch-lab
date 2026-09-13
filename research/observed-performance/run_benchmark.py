"""Repeatable bounded autonomy benchmark; preserves each study edition and all attempts.

Run from repository root: .venv/bin/python -m research.observed-performance.run_benchmark
Every execution creates new immutable editions. No original studies are resumed.
"""

import html
import json
from pathlib import Path

from methane.adaptation import DEFAULT
from methane.config import Config, Costs, Scenario
from methane.field_operations import FieldOperations
from methane.service_economics import ACTIVITY_VERSION, illustrative
from methane.services.configuration import ServiceSystem
from methane.services.controller import ServicePolicy
from methane.studies import STORE, create, publish, run_edition
from methane.uncertainty import VERSION
from methane.uncertainty_studies import protocol

ROOT = Path(__file__).resolve().parent


def fixture():
    return Config(
        scenario=Scenario(hours=24, horizon_hours=6, solver_seconds=0.05, variability=0.15),
        field_operations=FieldOperations(
            enabled=True,
            initial_soiling_fraction=0.18,
            soiling_per_day=0.003,
            mission_failure_probability=0.05,
        ),
        service_system=ServiceSystem(
            inspector="both",
            inspection_model="referenced-contact/1",
            cleaning_model="section-optical/1",
            cleaning_policy="condition",
            support_model="logistics/1",
            outcome_randomness="target-action-request/1",
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
        ),
        service_economics=illustrative(Costs(), version=ACTIVITY_VERSION),
        service_policy=ServicePolicy(
            maximum_wait_hours=6, maximum_candidates=4, comparison_seconds=0.1
        ),
    )


def specification(arm):
    return dict(
        schema_version=VERSION,
        seed=20260913,
        worlds=3,
        inner_seeds=[7, 17],
        design="factorial",
        adaptation={**DEFAULT, "mode": "adaptive" if arm == "adaptive" else "fixed"},
        rationale="Bounded workflow benchmark. Three explicit worlds, two matched event seeds. Stress values are illustrative, not empirical probabilities or calibration. No tuning on outcomes.",
        blocks=[
            dict(
                id="performance",
                paths=[
                    "weather.loss_fraction",
                    "field_operations.cleaning_removal_fraction",
                    "field_operations.mission_failure_probability",
                ],
                kind="values",
                rows=[[0.14, 0.9, 0.05], [0.35, 0.2, 0.05], [0.35, 0.2, 0.5]],
                visibility="disclosed" if arm == "disclosed" else "hidden",
                source="Explicit illustrative stress; uncertainty about plausible equipment ranges remains",
                rationale="Normal reference; poor conversion and weak cleaning; same mismatch with frequent mission interruption",
            )
        ],
    )


def main():
    entries = []
    for arm in ["disclosed", "fixed", "adaptive"]:
        c = fixture()
        spec = protocol(c.to_dict(), specification(arm))
        spec.update(
            title="Observed performance · " + arm,
            question="How does observation-driven adaptation change the response to incorrect conversion and service assumptions?",
            comparison="Same three explicit physical worlds and two event seeds across knowledge arms; each case compares all three dispatch strategies. No parameter fitting on outcomes.",
        )
        edition = create(basis=c.to_dict(), specification=spec)
        identifier = edition["edition_id"]
        print(arm, identifier, flush=True)
        # Incremental index makes an interrupted benchmark discoverable without rerunning completed work.
        entries.append(dict(arm=arm, edition_id=identifier))
        (ROOT / "latest.json").write_text(json.dumps(entries, indent=2) + "\n")
        run_edition(identifier)
        report = publish(identifier)
        entries[-1]["report_id"] = report["report_id"]
        entries[-1]["status"] = report["status"]
        (ROOT / "latest.json").write_text(json.dumps(entries, indent=2) + "\n")
    write_report(entries)


def write_report(entries):
    from methane.studies import archive_for, history, read_manifest

    rows = []
    physical = {}
    for entry in entries:
        manifest = read_manifest(entry["edition_id"])
        histories = history(entry["edition_id"])
        for case in manifest["cases"]:
            key = (case["uncertainty_world"]["index"], case["seed"])
            if key in physical:
                assert physical[key] == case["config"], (
                    "Knowledge arms must share the exact physical world"
                )
            physical[key] = case["config"]
            attempts = histories.get(case["case_id"], [])
            latest = attempts[-1] if attempts else {}
            if latest.get("status") != "complete":
                rows.append(
                    dict(
                        arm=entry["arm"],
                        world=key[0],
                        seed=key[1],
                        status=latest.get("status", "missing"),
                        error=latest.get("error"),
                    )
                )
                continue
            run = archive_for(entry["edition_id"], latest)
            for name, m in run["metrics"].items():
                trace = run["records"][name]
                rows.append(
                    dict(
                        arm=entry["arm"],
                        world=key[0],
                        seed=key[1],
                        status="complete",
                        controller=name,
                        methane_kg=m["methane_kg"],
                        pv_mae_kw=m["performance"]["one_step_pv_mae_kw"],
                        solar_multiplier=m["performance"]["ending_solar_multiplier"],
                        cleaning_estimate=trace[-1]["field_operations"]["performance_update"][
                            "after"
                        ],
                        cleanings=sum(r["field_operations"]["cleanings_completed"] for r in trace),
                        limited_solves=m["limited_solves"],
                        fallbacks=m["fallbacks"],
                        run_id=run["run_id"],
                        total_eur=m["total_eur"],
                        ending=m["ending"],
                    )
                )
    data = dict(
        schema_version="observed-performance-benchmark/1",
        editions=entries,
        rows=rows,
        scope="Workflow verification with illustrative assumptions, ideal current-weather and surface monitors, a short horizon and bounded solver budgets. Not field calibration or a hardware ranking.",
    )
    (ROOT / "results.json").write_text(json.dumps(data, indent=2) + "\n")
    esc = html.escape
    body = '<!doctype html><meta charset="utf-8"><title>Observed performance benchmark</title><style>body{background:#222;color:#ffa12b;font:15px monospace;margin:3em auto;max-width:1250px;padding:1em}a{color:inherit}p{line-height:1.7}table{width:100%;border-collapse:collapse}td,th{padding:.55em;border-bottom:1px solid #655134;text-align:left}.scroll{overflow:auto}</style>'
    body += "<h1>Managing incorrect performance assumptions</h1><p>" + esc(data["scope"]) + "</p>"
    body += "<p>Three matched knowledge arms: disclosed actual assumptions; hidden parameters with fixed estimates; hidden parameters with observation-driven adaptation. Each uses the same physical worlds and event seeds. World 0 is the nominal reference; world 1 combines increased conversion loss and weak cleaning; world 2 also raises mission interruption probability. Values are explicit stress assumptions, not measured rates.</p>"
    for e in entries:
        path = STORE / e["edition_id"] / "reports" / (e["report_id"] + ".html")
        body += (
            '<p><a href="'
            + esc(str(path))
            + '">'
            + esc(e["arm"])
            + " — complete immutable study write-up</a></p>"
        )
    body += '<h2>Every controller and case</h2><div class="scroll"><table><tr><th>Arm</th><th>World / seed</th><th>Controller</th><th>CH₄ / kg</th><th>One-step PV MAE / kW</th><th>Ending multiplier</th><th>Ending cleaning estimate</th><th>Limited / fallback solves</th></tr>'
    for r in rows:
        if r["status"] != "complete":
            body += '<tr><td colspan="8">' + esc(str(r)) + "</td></tr>"
            continue
        values = [
            r["arm"],
            f"{r['world']} / {r['seed']}",
            r["controller"],
            f"{r['methane_kg']:.3f}",
            f"{r['pv_mae_kw']:.3f}",
            f"{r['solar_multiplier']:.4f}",
            f"{r['cleaning_estimate']:.4f}",
            f"{r['limited_solves']} / {r['fallbacks']}",
        ]
        body += "<tr>" + "".join("<td>" + esc(v) + "</td>" for v in values) + "</tr>"
    body += "</table></div><h2>Interpretation boundaries</h2><p>The solar multiplier describes effective performance under assumed observed irradiance; it does not identify the physical cause. Cleaning estimates require informative work and the ideal surface monitor. A controller that defers work may collect no cleaning evidence. One-step power error includes changing weather and services, not only conversion mismatch. Different actions can expose different service events despite shared random streams.</p><p>Estimation accuracy does not imply greater methane production. Limited solves, different objectives, short comparison windows and ending inventories can change rankings. The linked write-ups retain costs, downtime, all ending inventories, incomplete cases and original inputs. Repeat this script to create new editions after changing the plant; retain the earlier editions for comparison.</p>"
    (ROOT / "report.html").write_text(body)
    return data


if __name__ == "__main__":
    main()
