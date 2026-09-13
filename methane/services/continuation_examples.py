"""Recorded matched cases for investigation, work and accepted operating tests."""

import argparse
import base64
import html
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.evidence import save
from methane.provenance import LOADED_FILES, LOADED_SOURCE
from methane.recovery import JOINT_VERSION
from methane.services.investigation_runs import CONTROLLER, fixture, summarize, weather_for, write
from methane.services.investigator import CONTINUATION_VERSION
from methane.simulation import run

VERSION = "investigation-continuation-cases/1"
CASES = {
    "trip-separate": ("trip-inspect", False),
    "trip-joint": ("trip-inspect", True),
    "damage-separate": ("damage-inspect", False),
    "damage-joint": ("damage-inspect", True),
    "unreadable-joint": ("unreadable", True),
    "shortage-joint": ("insufficient-power", True),
}


def evaluate(name):
    case, joint = CASES[name]
    config = fixture(case)
    if joint:
        config = replace(
            config,
            investigation_policy=replace(config.investigation_policy, version=CONTINUATION_VERSION),
            recovery_policy=replace(config.recovery_policy, version=JOINT_VERSION),
        )
    result = run(
        config,
        weather=weather_for(
            config, "power-shortage" if case == "insufficient-power" else "successful-procedure"
        ),
        strategies=[CONTROLLER],
    )
    summary = summarize(result, name, config)
    summary["version"] = VERSION
    summary["timeline"] = [
        dict(
            hour=r["hour"],
            requested_kw=r["requested"]["electrolyser_kw"],
            applied_kw=r["applied"]["electrolyser_kw"],
            investigation=r["decision"]["service_control"].get("investigation"),
            recovery=r["decision"].get("recovery_planning"),
        )
        for r in result["records"][CONTROLLER]
    ]
    return result, summary


def render(entries):
    esc = html.escape
    font = base64.b64encode(LOADED_FILES["assets/fonts/DepartureMono-Regular.woff2"]).decode()
    rows, sections = [], []
    for s in entries:
        episodes = (s.get("investigation") or {}).get("episodes", [])
        ending = episodes[-1] if episodes else {}
        confirmation = f"H{ending['confirmed_at']}" if "confirmed_at" in ending else "Unconfirmed"
        rows.append(
            f'<tr><td><a href="#{s["case"]}">{esc(s["case"])}</a></td><td>{s["methane_kg"]:.3f}</td><td>{s["ending_estimate"]["capacity_kw"]:.1f}</td><td>{confirmation}</td><td>{esc(ending.get("status", "No episode"))}</td></tr>'
        )
        tests = []
        for item in s["timeline"]:
            inv = item["investigation"] or {}
            episode = inv.get("episodes", [])
            episode = episode[-1] if episode else {}
            t = episode.get("accepted_test")
            if t:
                tests.append(
                    f"<tr><td>H{item['hour']}</td><td>{esc(episode['test_obligation']['work_order_id'])}</td><td>H{t['not_before_hour']}</td><td>H{t['start_hour']}–H{t['end_hour']}</td><td>{t['target_kw']:.0f}</td><td>H{t['due_hour']}</td></tr>"
                )
        detail = (
            (
                '<div class="scroll" tabindex="0" role="region" aria-label="Accepted test history"><table><thead><tr><th>Decision</th><th>After work</th><th>Earliest return boundary</th><th>Accepted test</th><th>kW</th><th>Deadline</th></tr></thead><tbody>'
                + "".join(tests)
                + "</tbody></table></div>"
            )
            if tests
            else "<p>No work-bound test window was accepted in this recording. The complete timeline retains independent tests and unresolved decisions.</p>"
        )
        service = s["service_costs"]["views"]
        cost = " · ".join(
            f"{esc(k)} service €{v['total_eur']:.2f}"
            if v["total_eur"] is not None
            else f"{esc(k)} cost incomplete"
            for k, v in service.items()
        )
        sections.append(
            f'<section id="{s["case"]}"><h2>{esc(s["case"].replace("-", " ").capitalize())}</h2><p>Execution: {esc(s["status"])}. Investigation: {esc(ending.get("status", "No episode"))}. {esc(ending.get("reason", ""))}</p><p>{cost}.</p>{detail}<p><a href="{s["case"]}/playback.html">Recorded animation</a> · <a href="{s["case"]}/summary.json">Original calculations, costs and ending inventories</a> · <a href="{s["case"]}/reproduction.zip">Offline reproduction bundle</a></p></section>'
        )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>From findings to accepted recovery tests</title><style>@font-face{{font-family:Departure;src:url(data:font/woff2;base64,{font})}}:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{background:#222;color:#ffad43;font:14px/1.75 Departure,monospace;margin:0}}main{{max-width:1120px;padding:40px 24px;margin:auto}}h1,h2{{font-weight:400}}a{{color:inherit}}p{{max-width:90ch;overflow-wrap:anywhere}}section{{border-top:1px solid #805620;margin-top:44px;padding-top:20px}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:640px}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #805620}}footer{{font-size:11px;overflow-wrap:anywhere;margin-top:40px}}@media(max-width:650px){{main{{padding:20px 12px}}h1{{font-size:23px}}}}</style><main><p>Dispatch Lab · Recorded workflow comparison</p><h1>From findings to accepted recovery tests</h1><p>Can a real inspection finding lead to a compatible repair and an operating test that waits for the work to finish? These recordings keep the conditional prediction, actual finding, work request, accepted test and observed outcome separate.</p><p>Each case runs for 32 hourly intervals with seed 7, synthetic weather, noiseless sensors and explicitly illustrative successful compatible procedures. The trip and damage pairs share plant, weather, faults and prices. They compare two policy packages: version 1's independent testing and full-nameplate conditional prediction, versus version 2's bounded prediction and jointly accepted work, charging and test schedule. This is not a one-variable ablation or a general policy ranking.</p><p>The damaged case has a stuck closed contact, so the first reset can be ineffective. The unreadable and shortage cases retain their unmet obligations. A completed execution means the time window ended; only recorded observer confirmation establishes estimated recovery. Positive-probability latent outcomes must agree before a conditional test is nominated. No successful repair hypothesis becomes an observation.</p><div class="scroll" tabindex="0" role="region" aria-label="Comparison results"><table><thead><tr><th>Case</th><th>Methane / kg</th><th>Ending estimate / kW</th><th>Confirmation</th><th>Investigation</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>{"".join(sections)}<section><h2>Scope and reproduction</h2><p>Both controllers use finite solver limits. Accepted tests may differ from the original conditional prediction after actual findings, completion times or resource constraints. That change is recorded, with the original investigation deadline. Later failed tests justify bounded follow-up; they do not create a calibrated post-intervention posterior.</p><p>Use the saved source and configuration for numerical reruns; timing-limited or tolerance-equivalent solutions can differ. Recorded playback remains immutable. Independent checks verify implemented conservation and accounting, not empirical reliability. Each archive preserves all ending plant and service inventories. Longer, matched, multi-seed studies with explicit terminal health and outstanding-work conditions remain necessary.</p></section><footer>{VERSION} · source {LOADED_SOURCE["content_hash"]}</footer></main></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    destination = parser.parse_args().directory
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Use a new directory; original recordings are immutable")
    destination.mkdir(parents=True, exist_ok=True)
    summaries = []
    for name in CASES:
        result, summary = evaluate(name)
        folder = destination / name
        folder.mkdir()
        summary["archive"] = save(result, folder).name
        make(result, folder / "reproduction.zip")
        write(folder / "playback.html", playback(result, LOADED_FILES))
        write(folder / "summary.json", json.dumps(summary, indent=2, allow_nan=False) + "\n")
        summaries.append(summary)
        print(name, summary["status"], summary["independent_check"]["passed"], flush=True)
    write(destination / "report.html", render(summaries))
    write(
        destination / "manifest.json",
        json.dumps(
            dict(
                version=VERSION,
                source=LOADED_SOURCE["content_hash"],
                cases=[
                    dict(
                        case=s["case"],
                        run_id=s["run_id"],
                        archive=s["case"] + "/" + s["archive"],
                        audit_passed=s["independent_check"]["passed"],
                    )
                    for s in summaries
                ],
            ),
            indent=2,
        )
        + "\n",
    )
    if not all(s["independent_check"]["passed"] for s in summaries):
        raise SystemExit("A recorded case failed its independent checks")
    print(destination / "report.html")


if __name__ == "__main__":
    main()
