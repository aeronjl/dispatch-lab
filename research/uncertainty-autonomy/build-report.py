"""Render the recorded qualification without running or changing a controller."""

import collections
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROGRAMMES = [
    ("a8710e0f41814ff5804fe2c605d47520", "First attempt · retained failures"),
    ("990adb658f8e4757b60b68708fd44399", "Corrected comparison · short operating window"),
    ("ce1a7e25c58742cbbfcefe51ba236fe3", "Service exposure · persistent equipment damage"),
]
esc = html.escape


def numeric(v):
    return "—" if v is None else f"{v:,.3f}" if isinstance(v, (int, float)) else str(v)


def metric(r):
    return next(iter(r.get("metrics", {}).values()), {})


def exposure(r):
    m = metric(r)
    orders = m.get("service_work", {}).get("orders", [])
    started = [o for o in orders if o.get("started_hour") is not None]
    return dict(
        dispatched_jobs=len(started),
        completed_jobs=sum(o["status"] in ("completed", "verified") for o in started),
        unverified_jobs=sum(o["status"] == "awaiting verification" for o in started),
        by_kind=dict(collections.Counter(o["kind"] for o in started)),
        field_energy_kwh=m.get("field_energy_kwh"),
        service_quantities=m.get("field_operations", {}).get("quantities", {}),
        obligations=m.get("service_control", {}),
    )


def table(headers, rows):
    return (
        '<div class="scroll" tabindex="0" role="region" aria-label="Recorded comparison"><table><thead><tr>'
        + "".join("<th>" + esc(h) + "</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + str(v) + "</td>" for v in row) + "</tr>" for row in rows
        )
        + "</tbody></table></div>"
    )


sections, data = [], []
for key, title in PROGRAMMES:
    path = ROOT / key / "qualification.json"
    if not path.exists():
        sections.append(
            f"<section><h2>{esc(title)}</h2><p>Not yet reported. No outcome is inferred.</p></section>"
        )
        continue
    p = json.loads(path.read_text())
    records = p["records"]
    audit_path = next((ROOT / key).glob("additional-audits/*/summary.json"), None)
    additional = json.loads(audit_path.read_text()) if audit_path else None
    audit_map = {e["edition_id"]: e for e in additional["entries"]} if additional else {}
    cases = []
    for r in records:
        cases.append(
            dict(
                edition_id=r["edition_id"],
                condition=r["condition"],
                arm=r["arm"],
                repeat=r["repeat"],
                seed=r["seed"],
                status=r["status"],
                source=r["source"],
                audit_passed=r.get("audit_passed"),
                additional_audit=audit_map.get(r["edition_id"]),
                exposure=exposure(r),
                methane_kg=r.get("methane_kg"),
                allocated_eur=metric(r).get("total_eur"),
                contribution_eur=metric(r).get("assumed_contribution_eur"),
                ending=r.get("ending"),
                unfinished_work=r.get("unfinished_work"),
                failures=r.get("failures"),
                limited_joint_solves=sum(
                    s.get("solver", {}).get("termination") == "time-limited"
                    for s in r.get("risk_solves", [])
                    if s.get("solver")
                ),
            )
        )
    noop = [
        r for r in records if r["condition"] == "no-op" and r["repeat"] == 1 and r.get("vectors")
    ]
    differences = []
    if len(noop) == 3:
        a = next(r for r in noop if r["arm"] == "fixed")
        for b in noop:
            fields = {
                k: max(
                    abs(float(x[k]) - float(y[k]))
                    for x, y in zip(a["vectors"], b["vectors"], strict=True)
                )
                for k in a["vectors"][0]
            }
            differences.append(
                dict(
                    arm=b["arm"],
                    maximum_difference_by_field=fields,
                    contribution_delta_eur=metric(b)["assumed_contribution_eur"]
                    - metric(a)["assumed_contribution_eur"],
                )
            )
    reviewed_groups = []
    if additional:
        for g in p["groups"]:
            pair = [r for r in records if r["condition"] == g["condition"] and r["arm"] == g["arm"]]
            eligible = (
                len(pair) == 2
                and all(
                    audit_map[r["edition_id"]]["current_audit_passed"]
                    and audit_map[r["edition_id"]]["physical_execution_status"] == "complete"
                    for r in pair
                )
                and len({(r["source"], r["inputs_hash"], r["weather_hash"]) for r in pair}) == 1
            )
            delta = (
                max(
                    abs(a[k] - b[k])
                    for a, b in zip(pair[0]["vectors"], pair[1]["vectors"], strict=True)
                    for k in a
                )
                if eligible
                else None
            )
            reviewed_groups.append(
                dict(
                    condition=g["condition"],
                    arm=g["arm"],
                    eligible=eligible,
                    maximum_trace_difference=delta,
                    stable=eligible and delta <= 1e-6 and pair[0]["work"] == pair[1]["work"],
                )
            )
    data.append(
        dict(
            programme=key,
            title=title,
            cases=cases,
            groups=p["groups"],
            no_op=differences,
            additional_audit=additional,
            separately_reviewed_repetitions=reviewed_groups,
        )
    )
    counts = dict(collections.Counter(r["status"] for r in records))
    audited = sum(r.get("audit_passed") is True for r in records)
    rows = []
    for g in p["groups"]:
        members = [r for r in cases if r["condition"] == g["condition"] and r["arm"] == g["arm"]]

        def span(key, members=members):
            vals = [r[key] for r in members if r.get(key) is not None]
            if not vals:
                return "—"
            return (
                numeric(min(vals))
                if max(vals) - min(vals) < 1e-6
                else numeric(min(vals)) + "–" + numeric(max(vals))
            )

        jobs = [r["exposure"]["dispatched_jobs"] for r in members]
        rows.append(
            [
                esc(g["condition"]),
                esc(g["arm"]),
                span("methane_kg"),
                span("allocated_eur"),
                span("contribution_eur"),
                esc(str(jobs)),
                str(g["stable_in_sample"]) if g["complete"] else "Not qualified in original report",
                str(g["unresolved_joint_solves"]),
                str(g["fallback_intervals"]),
            ]
        )
    attempt_rows = []
    for r in cases:
        ed = r["edition_id"]
        reports = sorted((ROOT.parents[1] / "runs/studies" / ed / "reports").glob("*.html"))
        link = (
            "../../" + str(reports[-1].relative_to(ROOT.parents[1]))
            if reports
            else f"../../runs/studies/{ed}/manifest.json"
        )
        attempt_rows.append(
            [
                f'<a href="{link}">{esc(r["condition"])} · {esc(r["arm"])} · repeat {r["repeat"]}</a>',
                esc(r["status"]),
                str(r["audit_passed"]),
                esc(json.dumps(r["exposure"]["by_kind"])),
                str(r["limited_joint_solves"]),
            ]
        )
    audit_note = ""
    if additional:
        audit_note = f'<p><strong>Separately identified correction:</strong> all {len(additional["entries"])} physical executions completed and pass the revised independent timing audit. Four original edition judgments remain invalid because their original checker used the reservation bound for a drive-test duration. Original judgments and decisions are unchanged. <a href="{audit_path.relative_to(ROOT)}">Additional audit, checker identity and original archive bindings</a>. With this correction, {sum(g["stable"] for g in reviewed_groups)} of {len(reviewed_groups)} repeated pairs are stable; this is a new interpretation, not a rewritten original report.</p>'
    sections.append(
        f'<section id="{key}"><h2>{esc(title)}</h2><p>{esc(p["scope"])}</p><p>Status counts: {esc(str(counts))}. Independent audits passed for {audited} archived attempts. A passed audit checks recorded mechanics; it does not turn an incomplete run into a completed one.</p>'
        + audit_note
        + table(
            [
                "Condition",
                "Policy",
                "CH₄ / kg",
                "Allocated / €",
                "Contribution / €",
                "Jobs per repeat",
                "Stable repeats",
                "Unresolved candidates",
                "Fallback intervals",
            ],
            rows,
        )
        + f'<p><a href="{key}/report.html">Detailed numerical report</a> · <a href="{key}/qualification.json">Recorded comparisons</a> · <a href="{key}/programme.json">Immutable protocol and source identities</a></p><details><summary>Individual attempts and original reports</summary>'
        + table(
            ["Attempt", "Status", "Audit", "Dispatched work", "Time-limited joint candidates"],
            attempt_rows,
        )
        + "</details></section>"
    )

(ROOT / "accounting.json").write_text(
    json.dumps(
        dict(version="uncertainty-autonomy-accounting/1", programmes=data),
        indent=2,
        allow_nan=False,
    )
    + "\n"
)
intro = """<p class="eyebrow">Dispatch Lab · implementation and qualification · 13 September 2026</p>
<h1>Uncertain work, observable evidence and joint decisions</h1>
<p class="lead">The broader uncertainty workflow is implemented. The experiments qualify its mechanics and expose limits in the comparison; they do not yet establish that adaptation or risk-aware planning improves plant management.</p>
<p>Four parts now work together: immutable repeated experiments; private service clocks and current support observations; recorded estimates that retain censoring and uncertainty; and bounded joint planning of service, process demand and charging. The first service system covers cleaning, inspection, bounded recovery, human work and supplies. No new repair capability is inferred.</p>
<nav><a href="#findings">What we learned</a><a href="#implementation">What changed</a><a href="#evidence">Verification</a><a href="#next">Next steps</a></nav>
<section id="findings"><h2>What these experiments actually tell us</h2>
<p><strong>Service exposure matters.</strong> All 36 attempts in the corrected short economic programme left optional cleaning unexecuted. A plausible no-work decision supplies no evidence about learning job durations. The “weak-cleaning” and “interruption” stress definitions also change weather conversion; their output differences cannot establish a cleaning or service-learning benefit. The table therefore reports dispatched jobs, and the second fixture introduces persistent equipment damage, inspection and required repair work without removing their ordinary costs.</p>
<p><strong>The null comparison is not perfectly neutral.</strong> With duration support and reference error collapsed, fixed and adaptive produced the same first-repeat trace. Risk-aware planning produced the same 40 kg of methane but a different power schedule and ending hydrogen inventory. At H9 its selected retained-work candidate had the same objective value as the fixed arm, despite a different first action. Duplicated scenarios, alternative optima, finite solver tolerances and receding horizons can change a trace without better information. The recorded per-field null differences are in the accounting file. A risk-aware advantage cannot be attributed solely to handling uncertainty on this evidence.</p>
<p><strong>There is no consistent policy winner.</strong> In the reference short run, fixed produced 40 kg and adaptive 38.054 kg. In the joint weak-cleaning/weather stress, fixed produced 36.771 kg and adaptive 37.328 kg. All 36 corrected attempts completed and passed their independent audits. Seventeen of eighteen within-policy pairs were stable; risk-aware interruption repeats ranged from 37.624 to 38.339 kg. That numerical spread limits interpretation of small policy differences.</p><p><strong>Failures remain visible.</strong> The first programme exposed an observation-history bug: two interrupted jobs could lose the distinction between their earlier histories. The scenario validator rejected these inputs before applying an invalid plan. The corrected source retains the observed job and availability boundary; dedicated tests and a new immutable programme exercise the correction. Original failed attempts remain linked below.</p>
<p><strong>Repair is not return to service.</strong> In the first fixed and adaptive damage runs, inspection and a module-substitution procedure execute, but the procedure remains unverified and methane output is zero. The fixed run starts substitution at H14 and completes the whole mission at H18.125; the adaptive run starts at H18 and completes at H22.125. The existing test obligation expires at H22, and a missed deadline applies the declared 24-hour retry interval. The H19 fixed decision explicitly reports that no validated combined service, charge and test plan was selected. The separately labelled retrospective truth shows that all three first-repeat damage-case procedures left capacity at 112.5 kW, below the 135 kW stable-load minimum. The controller does not receive that truth. It correctly retains an unverified condition, but timely follow-up testing and escalation remain a workflow weakness. <a href="recovery-timing.json">Original operands, service times and retrospective context</a>. Essential service obligations have priority over optional profit in this policy.</p><p><strong>Repeatability and realism answer different questions.</strong> Two numerical repeats share one seed and do not provide two independent environmental observations. A stable pair does not prove determinism, optimality, calibrated uncertainty or service value. Comparisons retain ending inventories, unresolved work and allocated versus decision-sensitive economics.</p></section>
<section id="implementation"><h2>What changed</h2>
<ul>
<li><strong>Execution:</strong> six private clock factors for travel, cleaning, inspection, repair, supply and support. Public upper bounds reserve resources and return energy; actual elapsed work determines energy, labour, area and consumable use. Interruptions preserve consumption and partial cleaning.</li>
<li><strong>Observations:</strong> current communications, route, dock, crew and reference availability; bounded surface and solar-reference error; completed and censored phase observations. Future outage endpoints and true clock factors remain outside the controller.</li>
<li><strong>Beliefs:</strong> versioned duration fits, evidence age, support violations, completion estimates and distinct pending repair verification. Repeated reports replace a packet rather than inventing new independent trials.</li>
<li><strong>Planning:</strong> fixed, adaptive and risk-aware modes; declared weather and duration branches, interruption stress, shared actions before observations distinguish outcomes, joint charging/test constraints, inventory reserves and expected/worst-branch objectives. Existing inspection and recovery mechanisms are reused.</li>
<li><strong>Interface and preservation:</strong> explicit opt-in choices in Studies; beliefs in revealed service inspection; recorded original-information alternatives; immutable source/input identities; independent offline checks and a readable recorded autonomy report. The main plant and solar illustrations are unchanged.</li>
</ul>
<p><a href="mechanisms.html">Mechanics and model boundaries</a> · <a href="offline-example/autonomous-services.html">Follow one recorded belief calculation</a> · <a href="offline-example/unpacked/playback.html">Play the saved cleaning example</a> · <a href="offline-example/reproduction.zip">Offline reproduction bundle</a></p>
<p>In the application, open Studies and design an uncertainty study; the “Service decisions under uncertainty” choice enables the new modes. Duration bounds and observation budgets travel with the saved specification. Existing runs retain their original model. Service inspectors reveal recorded evidence without adding labels to the main illustration.</p><p>The saved cleaning example is a 12-hour arithmetic fixture with constant 500 kW bus input and a 1.5× private cleaning duration. It checks accounting; it is not a measured weather or equipment calibration.</p></section>
<section id="evidence"><h2>Verification and its limits</h2>
<p>The final Python regression passed <strong>980 tests</strong> with two dependency-deprecation warnings. The renderer suite passed <strong>72 tests</strong>. Documentation bindings, generated catalogue/taxonomy and scoped production/test lint passed. Browser checks covered the new controls, invalidated previews, narrow screens and return navigation; the existing plant and solar screenshot checks passed without changing their baselines. Fixture-dependent browser cases that were not enabled were skipped, not counted as passes.</p>
<p>The exported cleaning example passed <strong>1,535 independent checks</strong> through the standard-library-only checker with Python isolated from installed dependencies. The separate retrieval/outage export passed <strong>10,006 checks</strong> with the corrected checker, while retaining the original archived execution and its original source. <a href="offline-retrieval-example/offline-check.json">Retrieval check</a> · <a href="offline-retrieval-example/reproduction.zip">Original execution with separately identified checker</a>. This is numerical and information-boundary verification, not empirical validation or a proof of the full controller.</p>
<p>The browser URL policy blocked a rendered preview of this local report. Its HTML and relative file links were checked; a screenshot review of this report is not claimed.</p><p><strong>The earlier interaction target is not met by this measurement:</strong> preview p95 was 631 ms, including cold requests; rendering p95 was 2.2 ms. The recorded fixture was 72 hours and a UI batch was not active, although the Python regression was competing for resources. This does not establish the 200 ms target or performance under an active UI batch. Optimizer comparisons have separate explicit computation limits.</p>
<p><a href="validation/python-tests.txt">Python test output</a> · <a href="offline-example/offline-check.json">Independent offline result</a> · <a href="validation/interaction-performance.json">Measured interaction samples</a> · <a href="accounting.json">Costs, inventories, exposure and null differences</a> · <a href="validation/manifest.json">Validation scope and artifact identities</a></p></section>
"""
next_steps = """<section id="next"><h2>Honest next steps</h2>
<ol>
<li><strong>Close the repair-to-verification loop.</strong> Revisit power reservation, test deadlines and retry timing together. Compare bounded alternatives that carry an unresolved test through a realistic night and preserve explicit deadlines and escalation. Require observed recovery or a clear unresolved outcome; do not restore capacity from a repair receipt.</li>
<li><strong>Make causal controller comparisons stricter.</strong> Canonicalise equivalent scenario formulations or use a documented secondary dispatch objective, then requalify the null control. Repeat selected decisions with larger budgets and explicit objective-gap checks. Do not pick a policy winner from the present short runs.</li>
<li><strong>Build a balanced exposure suite.</strong> Require declared opportunities for cleaning, inspection, successful and unsuccessful repair, interrupted work, replenishment and recovery verification; report whether each opportunity was actually encountered. Cross several event seeds, plant bottlenecks and seasonal European windows. Keep no-service and failed runs.</li>
<li><strong>Separate what is unknown from what varies.</strong> Current duration factors persist for an entire world. Extend the model with separately identified site/equipment effects and job-to-job variability only where evidence supports it. Validate duration, completion and measurement models against held-out observations before treating their weights as calibrated probabilities.</li>
<li><strong>Test the conservative planning boundaries.</strong> Shared visits retain full resource envelopes; possible stranding can rule out future charging even where contingent retrieval would help. Cleaning-effect intervals are recorded but not fully expanded into planning scenarios. Review which of these assumptions changes a decision before adding richer recourse, logistics or dependence models.</li>
<li><strong>Recover responsiveness and control evidence cost.</strong> Profile cold preview latency, planner/candidate overhead and archive duplication. Benchmark with an active batch, then optimise the measured bottleneck. Large populations of frozen editions are useful evidence but expensive in time and storage.</li>
</ol>
<p>Learned policies, broad degradation/maintenance economics and the remaining hardware families come after these gates. The earlier paused 14-family programme remains paused. Nothing here establishes that a robot can perform an unsupported repair, or that the illustrative distributions describe a real European site.</p></section>"""
style = """@font-face{font-family:Departure;src:url(../../assets/fonts/DepartureMono-Regular.woff2)}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#202020;color:#ffad43;font:15px/1.8 Departure,monospace}main{max-width:1180px;margin:auto;padding:56px 32px 90px}h1{font-size:34px;line-height:1.35;max-width:28ch;font-weight:400}h2{font-size:22px;line-height:1.45;font-weight:400}p,li{max-width:85ch}.lead{font-size:18px}a{color:#ffc16e;text-underline-offset:4px}section{border-top:1px solid #694d2b;margin-top:48px;padding-top:24px}nav{display:flex;flex-wrap:wrap;gap:12px 24px;margin:32px 0}.eyebrow{color:#bd8c4b;font-size:12px}li{margin:16px 0;padding-left:8px}strong{font-weight:400;color:#ffd495}.scroll{max-width:100%;overflow:auto;margin:24px 0}table{border-collapse:collapse;font-size:12px;min-width:900px;width:100%}th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #694d2b;vertical-align:top}th{font-weight:400;color:#ffd495}details{margin-top:24px}summary{cursor:pointer}a:focus-visible,summary:focus-visible,.scroll:focus-visible{outline:2px solid #ffce8c;outline-offset:4px}code{overflow-wrap:anywhere}@media(max-width:640px){main{padding:24px 18px 48px}body{font-size:13px}h1{font-size:26px}h2{font-size:19px}.lead{font-size:15px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}"""
body = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dispatch Lab · uncertain service system</title><style>'
    + style
    + "</style></head><body><main>"
    + intro
    + "".join(sections)
    + next_steps
    + "</main></body></html>"
)
(ROOT / "report.html").write_text(body)
print(ROOT / "report.html")
