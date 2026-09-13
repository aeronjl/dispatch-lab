"""Saved execution cases for bounded investigation, finding and follow-through."""

import argparse
import base64
import html
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.evidence import publish_completed, save, staging
from methane.provenance import LOADED_FILES, LOADED_SOURCE
from methane.reference import audit
from methane.service_economics import reprice_run
from methane.services.investigator import InvestigationPolicy
from methane.services.verification_examples import CONTROLLER, weather_for
from methane.services.verification_examples import fixture as base_fixture
from methane.simulation import run

VERSION = "executed-service-investigation-cases/1"
CASES = (
    "trip-inspect",
    "damage-inspect",
    "damage-direct",
    "trip-planned",
    "unreadable",
    "late-evidence",
    "insufficient-power",
)


def fixture(case):
    if case not in CASES:
        raise ValueError("Unknown investigation execution case")
    c = base_fixture("successful-procedure")
    return replace(
        c,
        scenario=replace(c.scenario, hours=32, horizon_hours=12),
        field_operations=replace(c.field_operations, reset_enabled=True),
        service_system=replace(
            c.service_system,
            inspector="fixed",
            inspection_delay_hours=20 if case == "late-evidence" else 0,
        ),
        faults=replace(
            c.faults,
            capacity_cause="equipment-damage" if case.startswith("damage-") else "resettable-trip",
            contact_stuck="closed" if case.startswith("damage-") else "none",
            fixed_reader_dropout=case == "unreadable",
        ),
        service_policy=replace(c.service_policy, maximum_wait_hours=24),
        investigation_policy=InvestigationPolicy(
            mode="direct-intervention"
            if case == "damage-direct"
            else "planned"
            if case == "trip-planned"
            else "inspect-first",
            comparison_seconds=0.5,
        ),
    )


def evaluate(case):
    c = fixture(case)
    result = run(
        c,
        weather=weather_for(
            c, "power-shortage" if case == "insufficient-power" else "successful-procedure"
        ),
        strategies=[CONTROLLER],
    )
    return result, summarize(result, case, c)


def summarize(result, case, c):
    """Summarise a recording without changing its original decisions or prices."""
    rows = result["records"][CONTROLLER]
    check = audit(result)
    costs = reprice_run(result, c.service_economics)["controllers"][CONTROLLER]
    summary = dict(
        version=VERSION,
        case=case,
        run_id=result["run_id"],
        source=LOADED_SOURCE["content_hash"],
        status=result["status"],
        failures=result["failures"],
        methane_kg=sum(r["applied"]["methane_kg"] for r in rows),
        ending_estimate=rows[-1]["diagnosis_after"] if rows else None,
        ending_plant=rows[-1]["state"] if rows else None,
        ending_services=rows[-1]["field_operations"]["state"] if rows else None,
        investigation=rows[-1]["decision"]["service_control"]["investigation"] if rows else None,
        costs={k: v for k, v in costs.items() if k != "services"},
        service_costs={
            k: v for k, v in costs["services"].items() if k in ("views", "quantities", "basis")
        },
        independent_check=check,
    )
    return summary


def write(path, value):
    with staging(path) as temporary:
        temporary.write_text(value)
        publish_completed(temporary, path)


def render(entries):
    esc = html.escape
    font = base64.b64encode(LOADED_FILES["assets/fonts/DepartureMono-Regular.woff2"]).decode()
    sections = []
    for summary in entries:
        episode = (summary.get("investigation") or {}).get("episodes", [])
        final = episode[-1] if episode else {}
        orders = (summary.get("ending_services") or {}).get("orders", [])
        rows = "".join(
            f"<tr><td>{esc(q['id'])}</td><td>{esc(q['kind'])}</td><td>H{q['created_hour']}</td><td>{esc(q['status'])}</td><td>{esc(q.get('followup_of', '—'))}</td></tr>"
            for q in orders
        )
        finding = final.get("finding", {})
        selection = final.get("selection", {})
        comparison = "".join(
            f"<li>{esc(a['strategy'])}: {esc(a['status'])}; assumed restoration probability {a['restoration_probability']:.3f}; {'eligible' if a['eligible'] else 'not eligible'}.</li>"
            for a in selection.get("candidates", [])
        )
        view = summary["service_costs"]["views"]
        money = " · ".join(
            f"{esc(key)} service €{v['total_eur']:.2f}"
            if v["total_eur"] is not None
            else f"{esc(key)} service cost incomplete"
            for key, v in view.items()
        )
        sections.append(
            f'<section id="{summary["case"]}"><h2>{esc(summary["case"].replace("-", " ").capitalize())}</h2><p>Experiment: {esc(summary["status"])}. Investigation: <strong>{esc(final.get("status", "No observed incident"))}</strong>.</p><p>{summary["methane_kg"]:.3f} kg methane · final estimated capacity {summary["ending_estimate"]["capacity_kw"]:.1f} kW. {money}.</p><p>{esc(final.get("reason", ""))}</p><ul>{comparison}</ul><p>{esc(finding.get("reason", "No returned contact finding"))}. {esc(final.get("belief_after_intervention", ""))}</p><p>Original episode deadline: H{final.get("due_hour", "—")}; observer confirmation: {final.get("confirmed_at", "not recorded")}.</p><div class="scroll" tabindex="0" role="region" aria-label="Recorded work"><table><thead><tr><th>Work</th><th>Action</th><th>Requested</th><th>Latest status</th><th>Follows</th></tr></thead><tbody>{rows}</tbody></table></div><p><a href="{summary["case"]}/playback.html">Recorded animated playback</a> · <a href="{summary["case"]}/summary.json">Results, inventories and original comparison</a> · <a href="{summary["case"]}/reproduction.zip">Offline reproduction bundle</a></p></section>'
        )
    links = " · ".join(f'<a href="#{c}">{esc(c.replace("-", " "))}</a>' for c in CASES)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>From inspection to verified recovery</title><style>@font-face{{font-family:Departure;src:url(data:font/woff2;base64,{font})}}:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{background:#222;color:#ffad43;font:14px/1.75 Departure,monospace;margin:0}}main{{max-width:1100px;margin:auto;padding:40px 24px}}h1,h2{{font-weight:400}}a{{color:inherit}}section{{border-top:1px solid #805620;margin-top:48px;padding-top:24px}}p,li{{max-width:90ch;overflow-wrap:anywhere}}.scroll{{overflow:auto}}table{{border-collapse:collapse;min-width:620px;width:100%}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #77522b}}nav{{line-height:2.3}}footer{{font-size:11px;overflow-wrap:anywhere;margin-top:60px}}@media(max-width:650px){{main{{padding:20px 12px}}h1{{font-size:23px}}}}</style><main><p>Dispatch Lab · Recorded execution cases</p><h1>From inspection to verified recovery</h1><p>A returned contact measurement can change the next service request. The resulting procedure still needs operating tests: a closed contact may belong to damaged equipment, and a completed reset need not restore capacity.</p><p>These seven 32-hour fixtures preserve requests, eligible findings, conditional predictions, failed tests and ending uncertainty. Prices and fault probabilities are illustrative. The three policy choices share the registered actions and observation interfaces; only the two damage cases are a matched inspect/direct comparison. This is a bounded workflow demonstration, not a broad controller ranking or calibrated reliability study.</p><p>The first action is selected from the saved comparison and rechecked with current work, charging and plant demand. Later operating-test scheduling uses the existing recovery policy; the conditional comparison's future test trajectory is a prediction rather than an accepted commitment. Incompatible, unsupported and unpriced alternatives remain incomplete. A later intervention does not silently renew the original static prior.</p><nav>{links}</nav>{"".join(sections)}<section><h2>What these cases establish</h2><p>Readings arrive before the actions they justify. Inspection completion, physical intervention and observer-confirmed capacity are separate facts. Episodes retain their first deadline. Missing information and exhausted attempts can end in escalation, with no successful recovery claimed.</p><p>Changed plant parameters require a new fixture edition and rerun. The saved numerical source and assumptions travel with each bundle. A numerical rerun may differ under finite solver time limits; playback retains the original recording. Independent checks cover the implemented physics, resource accounting and observation timing, not empirical reliability or global optimality.</p></section><footer>Model {VERSION} · source {LOADED_SOURCE["content_hash"]}</footer></main></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    dest = parser.parse_args().directory
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("Use a new directory; recorded experiment editions are immutable")
    dest.mkdir(parents=True, exist_ok=True)
    entries = []
    for case in CASES:
        result, summary = evaluate(case)
        folder = dest / case
        folder.mkdir()
        archive = save(result, folder)
        summary["archive"] = archive.name
        make(result, folder / "reproduction.zip")
        write(folder / "playback.html", playback(result, LOADED_FILES))
        write(folder / "summary.json", json.dumps(summary, indent=2, allow_nan=False) + "\n")
        entries.append(summary)
        print(case, summary["status"], summary["independent_check"]["passed"], flush=True)
    write(dest / "report.html", render(entries))
    write(
        dest / "manifest.json",
        json.dumps(
            dict(
                version=VERSION,
                source=LOADED_SOURCE["content_hash"],
                cases=[
                    dict(
                        case=e["case"],
                        run_id=e["run_id"],
                        archive=e["case"] + "/" + e["archive"],
                        audit_passed=e["independent_check"]["passed"],
                    )
                    for e in entries
                ],
            ),
            indent=2,
        )
        + "\n",
    )
    if not all(e["independent_check"]["passed"] for e in entries):
        raise SystemExit("An execution case failed its independent checks")
    print(dest / "report.html")


if __name__ == "__main__":
    main()
