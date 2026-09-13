"""Portable learning cases for observation-contingent service planning.

These packets are independent teaching fixtures, never reconstructed original
run evidence. Numerical reruns use only their sealed public planning inputs.
"""

import argparse
import base64
import copy
import html
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from methane.components import assemble
from methane.config import Costs, Models, Plant
from methane.evidence import publish_completed, staging
from methane.physics import State
from methane.provenance import LOADED_CAPSULE, LOADED_FILES, LOADED_SOURCE
from methane.sensing import Diagnosis
from methane.service_economics import ACTIVITY_VERSION
from methane.service_economics import illustrative as prices
from methane.services.coupling import identity
from methane.services.inspection_demo import fixture as inspection_fixture
from methane.services.investigation_belief import Assumptions, Hypothesis, illustrative
from methane.services.investigation_planning import compare
from methane.services.plant import PlantServices
from methane.services.snapshot import RecordedServices, capture

VERSION = "contact-investigation-learning/1"
CASES = (
    "fixed-reader",
    "mobile-interruption",
    "shared-contact",
    "reader-dropout",
    "late-crew",
    "insufficient-power",
)


def fixture(case, *, seconds=2):
    if case not in CASES:
        raise ValueError("Unknown investigation learning case")
    c = inspection_fixture()
    c = replace(
        c,
        field_operations=replace(
            c.field_operations,
            initial_soiling_fraction=0,
            repair_success_probability=0.6,
            mission_failure_probability=0.2 if case == "mobile-interruption" else 0,
        ),
        service_system=replace(
            c.service_system,
            support_model="logistics/1",
            crew_response_lead_hours=20 if case == "late-crew" else 0,
            crew_travel_hours=0.25,
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
        ),
    )
    rt = PlantServices(c.field_operations, c.service_system, 7, c.plant.electrolyser_kw)
    power = 50 if case == "insufficient-power" else 750
    rt.prepare(
        0,
        Diagnosis(225, active_incident=True, incidents=1, informative=True, tracking_residual=0.5),
        power,
    )
    belief = illustrative()
    if case == "shared-contact":
        belief = Assumptions(
            (
                Hypothesis("latch", "resettable-trip", 0.1),
                Hypothesis("damage", "equipment-damage", 0.1),
                Hypothesis("shared-contact", "damage-and-stuck-contact", 0.8),
            ),
            "assumption:learning-common-contact-sensitivity/1",
        )
    elif case == "reader-dropout":
        belief = Assumptions(
            (
                Hypothesis("latch", "resettable-trip", 0.5),
                Hypothesis("dropout-and-damage", "equipment-damage", 0.5, fixed_dropout=True),
            ),
            "assumption:learning-reader-dropout/1",
        )
    kind = "inspection-confirm" if case == "mobile-interruption" else "inspection"
    order = next(q["id"] for q in rt.orders if q["kind"] == kind)
    clock = datetime(2026, 4, 10, 10, tzinfo=UTC)
    forecast = dict(
        decision_hour=0,
        times=[(clock + timedelta(hours=i)).isoformat() for i in range(12)],
        source=dict(
            id="learning:declared-constant-power/1",
            initialized_at=clock.isoformat(),
            available_at=clock.isoformat(),
        ),
        pv_kw=[power] * 12,
        ambient_c=[20] * 12,
        deliveries_kg=[0] * 12,
    )
    snapshot = capture(rt)
    packet = dict(
        schema_version=VERSION,
        context="Learning example",
        fixture_id=case,
        source=LOADED_SOURCE["content_hash"],
        **snapshot,
        plant=asdict(c.plant),
        models=asdict(c.models),
        state=asdict(State.initial(c.plant)),
        forecast=forecast,
        capacity_kw=225,
        costs=asdict(c.costs),
        prices=prices(c.costs, version=ACTIVITY_VERSION),
        assumptions=asdict(belief),
        inspection_order=order,
        prefix=[],
        policy=dict(
            objective="methane", seconds=seconds, test_hours=2, risk_weight=0, terminal_minimum=None
        ),
        scope="A declared current 225 kW capacity estimate and illustrative static hypotheses. No injected fault schedule, future samples or private outcome draws are present. This is not original evidence from a completed run.",
    )
    packet["packet_id"] = identity(packet)
    return packet


def evaluate(packet):
    if packet.get("schema_version") != VERSION or packet.get("context") != "Learning example":
        raise ValueError("A supported learning packet is required")
    if identity({k: v for k, v in packet.items() if k != "packet_id"}) != packet.get("packet_id"):
        raise ValueError("Investigation learning packet integrity mismatch")
    original_id = identity(packet)
    rt = RecordedServices(packet["snapshot"], packet["catalogue"])
    assumption = copy.deepcopy(packet["assumptions"])
    assumption["hypotheses"] = tuple(Hypothesis(**h) for h in assumption["hypotheses"])
    plant = Plant(**packet["plant"])
    result = compare(
        rt,
        plant,
        State(**packet["state"]),
        packet["forecast"],
        packet["capacity_kw"],
        Costs(**packet["costs"]),
        Assumptions(**assumption),
        packet["inspection_order"],
        packet["prices"],
        prefix=packet["prefix"],
        **packet["policy"],
        components=assemble(plant, Models(**packet["models"])),
    )
    if identity(packet) != original_id:
        raise RuntimeError("Learning calculation changed its source packet")
    value = dict(
        schema_version=VERSION,
        context="Learning example",
        packet_id=packet["packet_id"],
        original_source=packet["source"],
        calculation_source=LOADED_SOURCE["content_hash"],
        source_matches=packet["source"] == LOADED_SOURCE["content_hash"],
        comparison=result,
    )
    value["result_id"] = identity(value)
    return value


def write_json(path, value):
    with staging(path) as temporary:
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
        return publish_completed(temporary, path)


def render(entries):
    esc = html.escape
    font_path = next(k for k in LOADED_FILES if k.endswith("DepartureMono-Regular.woff2"))
    font = base64.b64encode(LOADED_FILES[font_path]).decode()
    pages = []
    for index, entry in enumerate(entries):
        packet, result = entry["packet"], entry["result"]["comparison"]
        arms = []
        for name, strategy in result["strategies"].items():
            process = strategy.get("process", {})
            expected = process.get("expected")
            metrics = "No complete aggregate prediction."
            if expected:
                metrics = f"Predicted methane: {expected['methane_kg']:.3f} kg. Assumed operating contribution: €{expected['assumed_contribution_eur']:.2f}."
            rows = []
            for case in strategy.get("cases", []):
                projection = strategy["projections"][case["projection_id"]]
                money = projection["service_pricing"]["with_additions"]["decision"]["total_eur"]
                rows.append(
                    f"<tr><td>{esc(case['finding'])}</td><td>{esc(case['mechanism_hypothesis'])}</td><td>{case['probability']:.3f}</td><td>{esc(case['requested_remedy'])}</td><td>{'Restored' if case['restoration_hypothesis'] else 'Unchanged'}</td><td>{case['test_start_hour']}–{case['test_end_hour']}</td><td>€{money:.2f}</td><td>{'Rover recovery outstanding' if case['outstanding_recovery'] else 'No stranded rover in this branch'}; production recovery unverified</td></tr>"
                )
            conditions = esc(json.dumps(strategy.get("conditions", []), indent=2))
            solver = esc(json.dumps(process.get("solver", {}), indent=2))
            arms.append(
                f'<article><h3>{esc(name.replace("-", " ").capitalize())} · {esc(strategy["status"])}</h3><p>{metrics}</p><div class="scroll"><table><thead><tr><th>Finding</th><th>Hidden hypothesis</th><th>Weight</th><th>Conditional remedy</th><th>Physical hypothesis</th><th>Test hours</th><th>Service €</th><th>Ending obligations</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div><p>Conditions</p><pre>{conditions}</pre><p>Solver termination</p><pre>{solver}</pre></article>'
            )
        prior = " · ".join(
            f"{h['hypothesis_id']}: {h['probability']:.2f}"
            for h in packet["assumptions"]["hypotheses"]
        )
        pages.append(
            f'<section id="case-{index}" {"hidden" if index else ""}><h2>{esc(packet["fixture_id"].replace("-", " ").capitalize())}</h2><p>{esc(prior)}</p><p>Declared reliability: {packet["snapshot"]["config"]["repair_success_probability"]:.2f}; mobile interruption probability: {packet["snapshot"]["config"]["mission_failure_probability"]:.2f}. All probabilities are assumptions, not measured reliability.</p>{"".join(arms)}<p><a href="{esc(entry["packet_path"], quote=True)}">Original numerical inputs</a> · <a href="{esc(entry["result_path"], quote=True)}">Complete prediction and trajectories</a></p></section>'
        )
    options = "".join(
        f'<option value="case-{i}">{esc(e["packet"]["fixture_id"].replace("-", " ").capitalize())}</option>'
        for i, e in enumerate(entries)
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>When does inspection change the repair?</title>
<style>@font-face{{font-family:Departure;src:url(data:font/woff2;base64,{font})}}:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#222;color:#ffab39;font:14px/1.7 Departure,monospace}}main{{max-width:1300px;margin:auto;padding:40px 24px}}h1{{font-size:26px;font-weight:400}}h2,h3{{font-weight:400}}p{{max-width:86ch}}a{{color:inherit}}select{{font:inherit;padding:12px;background:#222;color:inherit;border:1px solid #956028;max-width:100%}}article{{margin-top:40px;border-top:1px solid #805620}}.scroll{{overflow:auto}}table{{border-collapse:collapse;font-size:12px;min-width:800px}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #644920;vertical-align:top}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 Departure,monospace;color:#d99c4b}}.flow{{display:flex;gap:12px;flex-wrap:wrap;margin:32px 0}}.flow span{{border:1px solid #956028;padding:12px}}footer{{margin-top:60px;font-size:12px;overflow-wrap:anywhere}}@media(max-width:650px){{main{{padding:20px 12px}}h1{{font-size:22px}}}}</style>
<main><p>Dispatch Lab · Learning example · Conditional predictions</p><h1>When does inspection change the repair?</h1><p>Inspecting a prepared contact can change the next compatible action. A closed contact permits a reset, but can also be a stuck contact on damaged equipment. These six saved comparisons preserve that ambiguity, unsuccessful procedures and unfinished recovery.</p>
<div class="flow" aria-label="Investigation sequence"><span>Current estimate + declared prior</span><span>→ Direct replacement</span><span>or → Inspect → Finding → Compatible remedy</span><span>→ Test → Actual confirmation still required</span></div>
<p>Each arm uses the same initial plant inventory, forecast, prices and hypothesis weights over twelve hours. Process requests are identical while observation histories are identical. Latent repair success changes predicted delivery, never the requested schedule. A two-hour nameplate test is planned after the procedure and return; the estimate stays derated until real tracking can confirm recovery.</p>
<label for="case">Explore a saved case</label><br><select id="case">{options}</select>{"".join(pages)}
<article><h2>What this establishes</h2><p>The executable comparison connects a bounded observation model to compatible conditional work, resource reservations, original weather inputs and process MPC. It exposes why an informative contact can save a visit, why a common contact failure defeats that shortcut, and why an interrupted inspection leaves additional work.</p><p>The predictions do not establish a deployed policy's reliability or annual savings. Inspection-dependent tests remain unverified at the horizon. No speculative inventory sale or automatic retrieval credit is assigned. If one positive-probability continuation is infeasible, its arm has no aggregate result; the other branches are retained without renormalizing. Solver limits remain visible.</p><h2>Next evidence required</h2><p>A run-level policy must rebuild the remedy from the actual finding, retain charging and existing test commitments, verify physical recovery, and replan unresolved work. A prior whose static-condition epoch ended after an intervention must be renewed explicitly or evolved by a validated transition model. These examples do not silently reset it. Comparative executed studies and the live inspector workflow remain separate completion gates.</p></article>
<footer>Source {esc(LOADED_SOURCE["content_hash"])}. <a href="manifest.json">Saved inputs, results and source capsule</a>. All six cases can be read offline. Numerical recalculation requires the captured application and its dependencies; finite solver runs may differ and must be reported as new results.</footer></main><script>document.getElementById('case').addEventListener('change',event=>{{for(const section of document.querySelectorAll('main>section'))section.hidden=section.id!==event.target.value;}});</script></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--seconds", type=float, default=2)
    args = parser.parse_args()
    destination = (
        args.directory
        or Path("build/services/investigation/recorded") / LOADED_SOURCE["content_hash"]
    )
    destination.mkdir(parents=True, exist_ok=True)
    if args.replay:
        result = evaluate(json.loads(args.replay.read_text()))
        print(write_json(destination / "recalculated.json", result))
        return
    entries = []
    for case in CASES:
        packet = fixture(case, seconds=args.seconds)
        result = evaluate(packet)
        folder = destination / case
        folder.mkdir(parents=True, exist_ok=True)
        packet_path = write_json(folder / "inputs.json", packet)
        result_path = write_json(folder / "prediction.json", result)
        entries.append(
            dict(
                packet=packet,
                result=result,
                packet_path=str(packet_path.relative_to(destination)),
                result_path=str(result_path.relative_to(destination)),
            )
        )
    capsule = write_json(destination / "source-capsule.json", LOADED_CAPSULE)
    manifest = dict(
        schema_version=VERSION,
        source=LOADED_SOURCE,
        source_capsule=capsule.name,
        entries=[
            dict(
                case=e["packet"]["fixture_id"],
                packet_id=e["packet"]["packet_id"],
                result_id=e["result"]["result_id"],
                packet=e["packet_path"],
                result=e["result_path"],
                status=e["result"]["comparison"]["status"],
            )
            for e in entries
        ],
    )
    manifest["manifest_id"] = identity(manifest)
    saved_manifest = write_json(destination / "manifest.json", manifest)
    with staging(destination / "report.html") as temporary:
        temporary.write_text(
            render(entries).replace('href="manifest.json"', f'href="{saved_manifest.name}"')
        )
        report_path = publish_completed(temporary, destination / "report.html")
    print(
        json.dumps(
            dict(report=str(report_path), manifest=str(saved_manifest), cases=manifest["entries"]),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
