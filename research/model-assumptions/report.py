"""Publish a read-only evidence report from saved runs; never executes a controller."""

import base64
import csv
import gzip
import html
import json
import statistics
from pathlib import Path

from methane.assumptions import registry, report_html, snapshot
from methane.config import Config, Costs, Plant
from methane.costing import allocation
from methane.provenance import LOADED_SOURCE, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
esc = html.escape


def table(headers, rows):
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + "".join("<th>" + esc(str(x)) + "</th>" for x in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + esc(str(x)) + "</td>" for x in row) + "</tr>" for row in rows
        )
        + "</tbody></table></div>"
    )


def main():
    latest = json.loads((HERE / "latest-experiments.json").read_text())
    directories = [HERE / latest["directory"]]
    extension = HERE / "latest-thermal-extension.json"
    if extension.exists():
        directories.append(HERE / json.loads(extension.read_text())["directory"])
    rows = []
    case_outcomes = []
    repriced = []
    for file in sorted(f for directory in directories for f in directory.glob("*/summary.json")):
        saved = json.loads(file.read_text())
        case_outcomes.append(
            dict(
                case=file.parent.name,
                status=saved["status"],
                audit=saved.get("audit_passed"),
                error=saved.get("error"),
            )
        )
        archive = file.parent / "result.json.gz"
        if not archive.exists():
            continue
        result = json.load(gzip.open(archive, "rt"))
        for strategy, m in result["metrics"].items():
            row = dict(
                case=file.parent.name,
                profile=saved["profile"],
                seed=saved["seed"],
                strategy=strategy,
                run_id=result["run_id"],
                status=result["status"],
                audit_passed=saved["audit_passed"],
                archive=str(archive.relative_to(HERE)),
                source=result["provenance"]["source"]["content_hash"],
            )
            for key in [
                "methane_kg",
                "curtailed_kwh",
                "reactor_starts",
                "electrolyser_starts",
                "forced_downtime_hours",
                "limited_solves",
                "fallbacks",
                "total_eur",
                "variable_and_wear_eur",
                "assumed_contribution_eur",
                "false_alarms",
                "uncertain_hours",
                "co2_rejected_kg",
            ]:
                row[key] = m[key]
            row.update({"ending_" + k: v for k, v in m["ending"].items()})
            rows.append(row)
            if saved["profile"] == "reference":
                original_hash = digest(result["records"][strategy])
                for price in [0.5, 1, 2]:
                    for co2 in [0.05, 0.15, 0.3]:
                        costs = Costs(
                            **{
                                **result["config"]["costs"],
                                "methane_eur_per_kg": price,
                                "co2_eur_per_kg": co2,
                            }
                        )
                        costs_report = allocation(
                            Plant(**result["config"]["plant"]), costs, result["records"][strategy]
                        )
                        assert digest(result["records"][strategy]) == original_hash
                        repriced.append(
                            dict(
                                seed=saved["seed"],
                                strategy=strategy,
                                methane_price=price,
                                co2_price=co2,
                                physical_trace_hash=original_hash,
                                allocated_eur=costs_report["total_eur"],
                                contribution_eur=costs_report["assumed_contribution_eur"],
                                scope="Repriced fixed actions, not rerun optimal dispatch",
                            )
                        )
    (HERE / "analysis.json").write_text(
        json.dumps(
            dict(cases=case_outcomes, trajectories=rows, repriced_fixed_traces=repriced), indent=2
        )
    )
    with (HERE / "trajectories.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    review = registry()
    bound = snapshot(Config().to_dict())
    checks = json.loads((HERE / "mechanism-checks.json").read_text())
    weather = json.loads((HERE / "weather-review.json").read_text())
    families = json.loads((ROOT / "docs/taxonomy-families.json").read_text())
    prior = json.loads((ROOT / "research/field-realism-review/review-context.json").read_text())
    current_files = LOADED_SOURCE["files"]
    checked_files = {p for g in review["groups"].values() for p in g["bindings"]}
    unchanged_prior = [
        p for p in checked_files if prior["source"]["files"].get(p) == current_files.get(p)
    ]
    manifest = dict(
        schema_version="model-assumption-review-result/1",
        review_edition=review["edition"],
        review_hash=digest(review),
        report_source=LOADED_SOURCE,
        study_sources=sorted(set(r["source"] for r in rows)),
        parameter_paths=len(review["parameters"]),
        mechanism_groups=len(review["groups"]),
        review_scope="Complete configuration inventory and consequential mechanism/evidence pass; not complete empirical calibration.",
        calibration_gate=review["calibration_gate"],
        new_case_groups=len(case_outcomes),
        new_trajectories=len(rows),
        all_case_outcomes=case_outcomes,
        thermal_checks=checks["thermal"]["count"],
        prior_review_unchanged_bound_files=unchanged_prior,
        production_defaults_changed=False,
        capabilities_changed=False,
        older_queue_resumed=False,
    )
    (HERE / "review-decision.json").write_text(json.dumps(manifest, indent=2))
    body = """<header><p class="eyebrow">Dispatch Lab / Evidence review / September 2026</p><h1>What can this plant<br>credibly tell us?</h1><p class="lead">The assumptions are now classified and traceable. The gate for real-plant calibration remains open.</p><p>This review keeps the existing illustrative plant and European sites. It checks model boundaries before tuning parameters, and separates physical relationships, chosen designs, equipment assumptions, policy choices and commercial inputs.</p></header>
<nav><a href="#findings">Findings</a><a href="#experiments">Sensitivity</a><a href="#weather">European weather</a><a href="#next">Evidence needed</a><a href="#families">Hardware families</a><a href="#assumption-review">Full register</a><a href="#sources">Sources & reproduction</a></nav>
<section id="findings"><h2>The consequential findings</h2>
<p><strong>Numerical correctness is much better established than equipment realism.</strong> The thermal equations, storage balances and ideal chemistry have independent checks. Those checks do not establish reactor kinetics, a realistic meter uncertainty budget, or the ability to perform a particular repair.</p>
<p>The register covers <strong>407 parameter paths and 19 mechanism groups</strong>, including optional policies, service assets, supplies and commercial contracts. Optional values remain optional. No equipment default or repair capability has been changed by this review.</p>
"""
    findings = [
        (
            "Reactor dynamics",
            "Thermal capacity and heat loss determine how long energy must be reserved. The fixture time constant is 3.75 hours. Neither parameter is measured; a mathematically stable single temperature does not establish an actual reactor operating envelope.",
        ),
        (
            "Electrolysis",
            "55 kWh/kg coincides with a DOE 2022 system benchmark. That does not identify a 450 kW device, reconcile a DC-bus/system boundary, or justify 40 kWh starts and 30% minimum load. Later DOE columns are targets, not measured performance.",
        ),
        (
            "Solar conversion",
            "The reference model imposes an output ceiling at module nameplate. At a deliberately cold, bright test point of −10°C and 1,200 W/m², its uncapped equation gives 1,021.68 kW, but execution returns 1,000 kW. A nameplate rating alone does not identify that limiter. The detailed model has a separate converter; keep the two interpretations explicit.",
        ),
        (
            "Measurement and diagnosis",
            "Hydrogen inventory noise is proportional to current production and becomes exactly zero when production stops. For a hypothetical independent 0.1 kg standard uncertainty on two tank readings, their difference has 0.141 kg uncertainty: 14.1% of a 1 kg interval flow, before outflow-meter error. The current 2% assumption is not a complete uncertainty budget.",
        ),
        (
            "Gas and water",
            "Buffers conserve mass but omit pressure, compression, leakage and usable heels. Purchased electrolyser water is a 12 L/kg allowance while reaction water consumption is 9 kg/kg. Those are separate boundaries, not interchangeable measurements.",
        ),
        (
            "Service value",
            "Fault onset, deposition, contact quality, task success, crew response and prices remain scenarios. A generic replacement or flow-sensor adjustment has no named part/procedure behind it. Better scheduling cannot validate that repair capability.",
        ),
    ]
    body += table(["Area", "Finding"], findings)
    body += (
        '<p>Source basis: <a href="'
        + review["sources"]["doe-pem"]["url"]
        + '">DOE system/stack targets</a>, <a href="'
        + review["sources"]["sam-pv"]["url"]
        + '">SAM/PVWatts model boundaries</a>, <a href="'
        + review["sources"]["uncertainty"]["url"]
        + '">JCGM uncertainty of differences</a>, and the source-bound implementation review in the full register.</p>'
    )
    body += f"<h3>Independent calculations</h3><p>{checks['thermal']['count']} combinations of thermal capacity, heat loss, initial/ambient temperature, heating, reaction and cooling agree with an independently integrated differential equation. Maximum difference: {checks['thermal']['maximum_error_K']:.2g} K (tolerance 10⁻⁷ K). Some cases intentionally lie outside the operating band; this tests the thermal helper, not feasible dispatch.</p>"
    body += '<p>Using NIST molecular weights instead of the rounded fixture changes the hydrogen-per-methane ratio by about 0.52%, CO₂ by 0.24% and reaction heat per kilogram by 0.26%. These are documented approximations; the larger unknowns are conversion, thermal hardware and auxiliary loads. No condensation or recycling credit is inferred. <a href="https://webbook.nist.gov/chemistry/">NIST Chemistry WebBook</a>.</p></section>'
    body += """<section id="experiments"><h2>Conclusions change across assumptions</h2><p>Five deliberately chosen profiles × three seeds × three controllers: 45 controller trajectories, each 48 hours with a 12-hour planning horizon and 0.2-second solve budget. These joint stresses probe reversals; they are not confidence intervals or a probability-weighted forecast. The saved case index retains all outcomes and solver limitations.</p><p>The reference uses the existing defaults. Retentive combines half thermal mass/loss/start cost, 95% battery efficiency and 50 kWh/kg electrolysis. Demanding combines double thermal mass/loss/start cost, 85% efficiency and 65 kWh/kg. Storage-constrained halves battery/H₂ capacity and CO₂ replenishment. Coupled stress combines demanding and storage-constrained. These are hypothetical packages, not named commercial plants.</p>"""
    summary = []
    for profile in ["reference", "retentive", "demanding", "storage-constrained", "coupled-stress"]:
        for strategy in ["Greedy", "MPC · methane", "MPC · economics"]:
            subset = [r for r in rows if r["profile"] == profile and r["strategy"] == strategy]
            summary.append(
                [
                    profile,
                    strategy,
                    f"{statistics.mean(r['methane_kg'] for r in subset):.1f}",
                    f"{min(r['methane_kg'] for r in subset):.1f}–{max(r['methane_kg'] for r in subset):.1f}",
                    f"{statistics.mean(r['assumed_contribution_eur'] for r in subset):.1f}",
                    sum(r["limited_solves"] for r in subset),
                    sum(r["fallbacks"] for r in subset),
                ]
            )
    body += table(
        [
            "Profile",
            "Controller",
            "Mean CH₄ kg",
            "Seed range kg",
            "Mean contribution EUR",
            "Limited solves",
            "Fallbacks",
        ],
        summary,
    )
    body += f'<p>Recorded outcomes: {len(case_outcomes)} run groups, {len(rows)} controller trajectories; {sum(c["status"] == "complete" for c in case_outcomes)} complete groups and {sum(c["audit"] is True for c in case_outcomes)} independent audits passed. All attempts remain in <a href="analysis.json">the case index</a>.</p>'
    extra = []
    for profile in ["slow-cooling", "fast-cooling"]:
        for strategy in ["Greedy", "MPC · methane", "MPC · economics"]:
            subset = [r for r in rows if r["profile"] == profile and r["strategy"] == strategy]
            if subset:
                extra.append(
                    [
                        profile,
                        strategy,
                        len(subset),
                        round(statistics.mean(r["methane_kg"] for r in subset), 1),
                        round(statistics.mean(r["assumed_contribution_eur"] for r in subset), 1),
                        sum(r["limited_solves"] for r in subset),
                        sum(r["fallbacks"] for r in subset),
                    ]
                )
    if extra:
        body += "<h3>A second pass varies heat retention</h3><p>The first profiles scaled C and UA together and therefore kept the 3.75-hour cooling time constant. After inspecting that limitation, an explicitly exploratory amendment added slow cooling (C=0.6, UA=0.04; 15 hours) and fast cooling (C=0.15, UA=0.16; 0.9375 hours), preserving the other reference defaults. These cases use the same seeds/weather and unchanged scientific kernels; source/presentation editions are separately recorded. The amendment was specified after the first results, not preregistered as confirmation.</p>"
        body += table(
            [
                "Profile",
                "Controller",
                "Seeds",
                "Mean CH₄ kg",
                "Mean contribution EUR",
                "Limited solves",
                "Fallbacks",
            ],
            extra,
        )
        body += '<p><a href="thermal-extension.json">Recorded amendment</a>. These extra cases change thermal inertia and steady heat demand as well as the cooling time constant; they are not a one-variable causal attribution.</p>'
    body += """<p><strong>The ranking reverses.</strong> Methane MPC trails Greedy on mean output in the reference and storage-constrained profiles, but leads in the other three. These differences include the finite solver budget and fallback behaviour; they do not isolate an intrinsic algorithm advantage. Only three seeds were tested.</p><p>Economic MPC has the highest mean assumed operating contribution in each of these five profiles, while producing less methane than at least one alternative. That statement is conditional on the original prices and wear rules. Ownership allocations are separate, and this result is not a claim about profitability.</p><p>Ending inventories matter. In the storage-constrained Greedy case, 650 kg available CO₂ divided by the ideal 2.75 kg/kg ratio gives a 236.36 kg methane ceiling; all three seeds reach it. More cleaning or generation cannot increase output across that boundary without more feedstock. Detailed case tables retain all ending inventories, temperature, starts, forced downtime, rejected deliveries and solver limits.</p>"""
    body += '<p><a href="trajectories.csv">All trajectories and ending inventories (CSV)</a> · <a href="analysis.json">Detailed outcomes and fixed-trace repricing (JSON)</a> · <a href="protocol.json">Study protocol</a></p>'
    body += "<h3>Prices without changing history</h3><p>81 combinations reprice the nine reference traces over methane values of €0.5/1/2 per kg and CO₂ prices of €0.05/0.15/0.30 per kg. Physical-trace hashes remain unchanged. These are accounting comparisons of fixed actions; obtaining a policy optimized for the new prices requires a rerun.</p></section>"
    body += '<section id="weather"><h2>European weather: useful, with a boundary</h2><p>All nine ten-day windows loaded from the saved cache without network access. This compares the saved daily 00 UTC ECMWF issue eligible under a six-hour publication lag with ERA5-derived DC generation. It does not compare against measured array output. The table uses a six-hour decision lead; nighttime hours are included.</p>'
    body += table(
        ["Site", "Window start", "Reference DC kWh", "Bias kW", "RMSE kW", "Status"],
        [
            [
                w["site"],
                w["start"],
                round(w.get("reference_dc_kwh", 0)),
                round(w["forecast_vs_reanalysis"]["6"]["bias_kw"], 1),
                round(w["forecast_vs_reanalysis"]["6"]["rmse_kw"], 1),
                w["status"],
            ]
            for w in weather["windows"]
        ],
    )
    body += '<p>The cached plant-weather responses lack the wind and precipitation channels needed to substantiate cleaning eligibility. London, Seville and Copenhagen therefore provide different radiation/temperature histories, but do not yet establish regional robot availability. No synthetic weather was substituted. <a href="weather-review.json">Cache identities, availability and all lead-time results</a>.</p></section>'
    body += """<section id="next"><h2>What would close the calibration gate?</h2><p>There is no matching operating-plant measurement dataset in the project. Public reference and validation data can test a generic mechanism, but cannot calibrate unnamed site equipment. We should first select one coherent reference package and collect evidence against explicit electrical, thermal, gas and service boundaries.</p>"""
    data_plan = [
        (
            "1. Reactor",
            "Matched reactor type, geometry, materials, insulation and operating envelope; heater power and multi-point temperatures through warm-up, steady hold, cool-down and production load steps.",
            "Fit thermal mass and heat loss jointly with sensor offsets; quantify identifiability. Hold out complete cycles and load regimes. Add feed sensible heat/kinetics if residuals show systematic mismatch.",
        ),
        (
            "2. Electrolyser and storage",
            "One system specification, pressure/purity boundary, load/efficiency/startup/standby traces, usable gas/battery capacity and conversion/compression loads.",
            "Fit only inside tested operating ranges; validate at different loads, SOC and temperatures. Do not combine best numbers from different devices.",
        ),
        (
            "3. Observation model",
            "Named flow, pressure/temperature/inventory and power meters; calibration/reference records, synchronization, drift, zero-flow behaviour and covariance.",
            "Build the uncertainty budget before tuning thresholds. Test blind normal, equipment-fault, sensor-fault and common-cause cases; report uncertainty and unidentifiable cases.",
        ),
        (
            "4. PV and site",
            "Module/mounting/converter/loss definitions, POA irradiance, DC power, cell temperature, wind/rain, paired clean references and local soiling histories.",
            "Separate weather-resource errors from conversion errors. Split validation by complete weather/seasonal windows. Sandia PVPMC data is a candidate for generic model benchmarking, not our plant calibration.",
        ),
        (
            "5. Complete service system",
            "Named hardware + supported fault/action matrix, engineered access and test interfaces, consumables, crew and supplier resources, weather restrictions, task time/energy/outcome logs.",
            "Block unsupported capability claims. Fit duration/failure distributions only with exposure and censored outcomes; retain common causes and unsuccessful tasks.",
        ),
        (
            "6. Economics and external validity",
            "Dated scoped equipment and service quotes, delivered feedstock, tariffs, replacement histories and realistic annual fault exposure.",
            "Keep allocation, action costs and actual cash costs separate. Use joint uncertainty scenarios and held-out operating windows before procurement or annual ROI claims.",
        ),
    ]
    body += table(
        ["Priority", "Evidence to obtain", "Calibration and validation method"], data_plan
    )
    body += "<p>The practical next engineering step is the observation-model correction and an explicit equipment/reference boundary, followed by reactor and electrolyser evidence. A structural change to gas pressure, reaction conversion, auxiliary loads or repair authority should be reviewed as a model revision before further controller studies. The broader programme remains paused.</p></section>"
    body += '<section id="families"><h2>All fourteen hardware families remain bounded</h2><p>The earlier field feasibility review is retained, with its original sources and code identity. It is background evidence rather than new performance calibration. No family classification grants execution authority.</p>'
    body += table(
        [
            "Family",
            "Feasibility",
            "Permitted scope",
            "Unavailable scope",
            "Prerequisites and support",
        ],
        [
            [
                f["name"],
                f["feasibility"],
                f["permitted_scope"],
                f["unavailable_scope"],
                f["prerequisites"] + " " + f["support"],
            ]
            for f in families["families"]
        ],
    )
    body += '<p><a href="../field-realism-review/report.html">Original field review, 31 findings and conditional experiments</a>. Its original result identities are preserved.</p></section>'
    body += report_html(bound, source_details=False)
    body += '<section id="sources"><h2>Sources, scope and reproduction</h2><p>In the app: Explore component → Assumptions → mechanism → parameter. Older archives require the labelled Current catalogue context. The simulation illustration and its labels remain unchanged.</p><p>Validation: 238 targeted Python tests and 8 JavaScript tests passed. Browser checks cover progressive evidence views, keyboard/narrow-screen use, return navigation, offline reading and original plant/solar artwork. The standalone reproduction checker passed 114 assertions. These scoped outcomes are separate from empirical calibration. <a href="../../docs/assumption-review-validation.md">Detailed validation record and limitations</a>.</p><p>Primary evidence supports only the associated claim. Reference defaults and source targets are not empirical intervals. Some primary pages were available only as indexed extracts; those access limits are recorded below.</p>'
    for s in review["sources"].values():
        link = (
            '<a href="' + esc(s["url"]) + '">' + esc(s["title"]) + "</a>"
            if s["url"].startswith("https://")
            else esc(s["title"])
        )
        body += f'<article><h3>{link}</h3><p>{esc(s["finding"])}</p><p>{esc(s["applicability"])}</p><p class="small">{esc(s["access"])}</p></article>'
    body += '<h3>Saved evidence</h3><p><a href="review-decision.json">Review decision and source bindings</a> · <a href="mechanism-checks.json">Independent calculations</a> · <a href="weather-review.json">Weather audit</a> · <a href="checks.xml">Automated test outcomes</a></p><p>Each numerical run contains its original configuration, complete actions, weather and executable source capsule. The source may predate final presentation edits; scientific implementation hashes are retained for comparison. The register separately invalidates its mechanism reviews when bound source changes. Old archives do not acquire this review retroactively.</p><p>To reproduce, use the archived run/source bundle for an exact recorded example. The research scripts and frozen protocol are saved alongside this report. New numerical results require a new source/input identity. No old study queue was resumed.</p></section>'
    font = base64.b64encode(
        (ROOT / "assets/fonts/DepartureMono-Regular.woff2").read_bytes()
    ).decode()
    style = f"@font-face{{font-family:Departure;src:url(data:font/woff2;base64,{font})}}"
    style += """*{box-sizing:border-box}html{scroll-behavior:smooth}body{background:#222;color:#dac5a7;font:15px/1.8 Departure,monospace;margin:0}main{max-width:1140px;margin:auto;padding:60px 6vw 100px}header{padding:30px 0 60px;max-width:900px}h1{font-size:clamp(32px,5vw,60px);line-height:1.2;font-weight:400;color:#ffac43}h2{font-size:26px;line-height:1.4;color:#ffb552;font-weight:400}h3{font-size:17px;color:#ffbd6a;font-weight:400;margin-top:30px}.lead{font-size:20px;color:#ffd198}.eyebrow,.small{font-size:12px;color:#b29978}p{max-width:85ch}a{color:#ffb552;text-underline-offset:4px}nav{display:flex;gap:12px 26px;flex-wrap:wrap;border-block:1px solid #785435;padding:20px 0}section{padding-top:55px;margin-top:30px;border-top:1px solid #785435}article{padding-bottom:12px}table{width:100%;border-collapse:collapse;font-size:12px;line-height:1.65}th{color:#ffb552;text-align:left;font-weight:400}td,th{border-bottom:1px solid #62472f;padding:12px 9px;vertical-align:top;overflow-wrap:anywhere}.table-wrap{overflow:auto}strong{color:#f1d4af;font-weight:400}#assumption-review table td:first-child{width:30%;max-width:240px;overflow-wrap:anywhere}@media(max-width:650px){main{padding:24px 6vw 60px}table{font-size:11px}h2{font-size:22px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}"""
    (HERE / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dispatch Lab — Assumptions and evidence review</title><style>'
        + style
        + "</style><main>"
        + body
        + "</main></html>"
    )
    (HERE / "report.md").write_text("""# Assumptions and evidence review — 12 September 2026

The platform-wide review is complete; empirical calibration remains open because there are no matched plant/service observations. All 407 reference parameter paths and 19 consequential mechanism groups are classified, including optional contracts. Existing physics defaults, repair capabilities, old archives and the paused programme queue are unchanged.

The most consequential gaps are reactor heat/operating assumptions, the electrolyser system boundary, unrealistic inventory metrology at low flow, implicit reference-PV clipping, omitted storage/compression loads and cause-specific repair capability. Literature benchmarks do not close these gaps.

The initial conditional study executed 45 controller trajectories (five joint profiles, three seeds, three strategies). An explicitly exploratory amendment adds 18 trajectories with slower/faster cooling. Outcomes, independent audits and all limitations are retained in the full report. Methane MPC/Greedy mean-output rankings reverse across profiles. 384 thermal cases passed independent integration checks. Nine European ten-day windows replayed offline; their cached data does not contain cleaning wind/rain channels. Fixed-trace repricing preserves recorded actions.

[Read the full report](report.html), [all trajectories](trajectories.csv), [parameter and mechanism registry](../../docs/assumption-review.json), [protocol](protocol.json), [review/source decision](review-decision.json).

In the app: Explore component → Assumptions → mechanism → parameter. Older runs require the labelled Current catalogue context. Current Model essays also include the scoped parameter review. New run catalogues capture the review once and reproduction exports retain it.

Next: choose a coherent reference equipment package; repair the observation model; acquire/fit reactor and electrolyser data with held-out validation. Keep capabilities without a named device/procedure explicitly conditional.
""")
    print(HERE / "report.html")


if __name__ == "__main__":
    main()
