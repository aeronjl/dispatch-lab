"""Version-bound model explanations, readable lineage and portable reports."""

import copy
import hashlib
import html
import json
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from methane.config import Costs, Scenario, Sensors
from methane.contracts import SPECS
from methane.model_topics import TOPICS
from methane.provenance import LOADED_FILES, LOADED_SOURCE, digest

ROOT = Path(__file__).resolve().parent.parent
REVIEW = "docs/model-review.json"


def bindings():
    result = {}
    for key, t in TOPICS.items():
        # Teaching policy changes also require narrative review. Freeze the bytes
        # loaded by this process, not an edited file underneath a running server.
        paths = ["methane/" + f for f in t["files"]] + [
            "methane/learning.py",
            "methane/model_topics.py",
            "methane/service_topics.py",
            "methane/config.py",
            "methane/contracts.py",
            "methane/physics.py",
            "methane/reactor.py",
            "methane/battery.py",
            "methane/electrolyser.py",
            "methane/storage.py",
            "methane/costing.py",
            "methane/service_economics.py",
            "methane/field_operations.py",
            "methane/faults.py",
            "methane/recovery.py",
            "methane/ports.py",
            "methane/uncertainty.py",
            "methane/autonomy.py",
            "methane/autonomy_reference.py",
            "methane/duration_population.py",
            "methane/duration_calibration.py",
            "methane/duration_reference.py",
            "docs/equipment-job-uncertainty.md",
            "methane/autonomy_studies.py",
            "docs/uncertain-service-system.md",
            "plant.py",
            "economics.py",
        ]
        paths += [
            p for p in LOADED_FILES if p.startswith("methane/services/") and p.endswith(".py")
        ]
        result[key] = dict(
            contracts={s: digest(SPECS[s].to_dict()) for s in t["specs"]},
            implementations={p: hashlib.sha256(LOADED_FILES[p]).hexdigest() for p in paths},
            narrative=digest(t),
        )
    return result


def check_freshness():
    expected = bindings()
    recorded = json.loads(LOADED_FILES.get(REVIEW, b"{}"))
    stale = [k for k in expected if expected[k] != recorded.get(k)]
    if stale:
        raise ValueError("Model explanations need review: " + ", ".join(stale))
    if set(default_examples()) != set(TOPICS):
        raise ValueError("Saved learning examples are missing or stale; regenerate after review")
    for t in TOPICS.values():
        for p in t["passages"]:
            for term, _ in p["terms"]:
                if term not in p["equation"]:
                    raise ValueError("Unbound equation term: " + term)
        for link in t["sources"]:
            if not link.startswith("https://"):
                raise ValueError("Reference must use HTTPS")
    return True


def evidence_claims(topic):
    """Never promote another build's passing tests to this source."""
    path = ROOT / "build/engineering/current/evidence-catalogue.json"
    report = json.loads(path.read_text()) if path.exists() else {}
    teaching_path = ROOT / "build/model/evidence.json"
    teaching = json.loads(teaching_path.read_text()) if teaching_path.exists() else {}
    teaching_claim = teaching.get("topics", {}).get(topic)
    same = report.get("source", {}).get("content_hash") == LOADED_SOURCE["content_hash"]
    artifact = next((x for x in report.get("checks", []) if x.get("name") == "python"), None)
    status = (
        "missing"
        if not artifact
        else "stale"
        if not same
        else "passed"
        if artifact.get("passed")
        else "failed"
    )
    claims = [
        dict(
            id=topic + "/numerical/1",
            claim="Numerical and boundary checks for this implementation",
            status=status,
            method="Component tests and independent reference cases; see linked artifacts for tested domains.",
            artifact="build/engineering/current/evidence-catalogue.json",
            source=report.get("source", {}).get("content_hash"),
            applies_to=LOADED_SOURCE["content_hash"],
            scope="Suite-level outcome; this does not imply every parameter combination is verified.",
        ),
        dict(
            id=topic + "/empirical/1",
            claim="Calibrated against an operating plant",
            status="unsupported",
            method="No empirical calibration dataset is supplied.",
            scope="Numerical verification is not plant calibration.",
        ),
    ]
    if teaching_claim:
        claims[0] = {
            **teaching_claim,
            "id": topic + "/teaching-checks/1",
            "claim": "Executable teaching fixture and linked independent checks",
            "status": teaching_claim["status"]
            if teaching.get("source") == LOADED_SOURCE["content_hash"]
            else "stale",
            "source": teaching.get("source"),
            "artifact": "build/model/evidence.json",
            "method": "Executed pytest cases listed below; the fixture checks its production audits",
            "scope": "The named cases and their tested inputs; not empirical plant calibration or exhaustive parameter coverage.",
        }
    if topic == "reactor":
        a = next((x for x in report.get("checks", []) if x.get("name") == "formal.json"), None)
        claims.append(
            dict(
                id="reactor/formal/1",
                claim="Minimum-run properties in a finite operating-state abstraction",
                status="missing"
                if not a
                else "stale"
                if not same
                else "passed"
                if a.get("passed")
                else "failed",
                method="TLC bounded model checking",
                scope="Commitments 1–4 in the checked abstraction; not a proof of continuous chemistry or complete plant control.",
            )
        )
    return claims


@lru_cache(maxsize=1)
def _catalogue():
    from methane.assumptions import for_topic, freshness, registry
    from methane.learning import defaults

    bound = bindings()
    assumption_review = registry()
    for key, status in freshness(assumption_review).items():
        assumption_review["groups"][key]["review_status"] = status
    reviewed = json.loads(LOADED_FILES.get(REVIEW, b"{}"))
    pages = {}
    for key, t in TOPICS.items():
        specs = {s: SPECS[s].to_dict() for s in t["specs"]}
        assumptions = list(t["assumptions"])
        for s, spec in specs.items():
            assumptions += [
                dict(id=f"{s}/assumption/{i}", text=value)
                for i, value in enumerate(spec["assumptions"])
            ]
        pages[key] = {
            **copy.deepcopy(t),
            "contracts": specs,
            "assumptions": assumptions,
            "sources": sorted(
                set(t["sources"] + [r for s in specs.values() for r in s["references"]])
            ),
            "defaults": defaults(key),
            "review_status": "reviewed" if reviewed.get(key) == bound[key] else "stale",
            "bindings": bound[key],
            "evidence": evidence_claims(key),
            "assumption_review": for_topic(assumption_review, key),
        }
        if key in (
            "cleaning",
            "inspection",
            "recovery",
            "charging",
            "logistics",
            "service_costs",
            "service_uncertainty",
        ):
            pages[key]["configuration_reference"] = {
                p["path"]: {
                    "reference_default": p["reference_default"],
                    "unit": p.get("unit"),
                    "evidence_status": p["evidence_status"],
                }
                for p in pages[key]["assumption_review"]["parameters"]
            }
        elif not specs:
            pages[key]["configuration_reference"] = asdict(
                Sensors() if key == "diagnosis" else Costs() if key == "economics" else Scenario()
            )
    return dict(
        schema_version="dispatch-lab/model-documentation/1",
        source=LOADED_SOURCE["content_hash"],
        topics=pages,
        scope="Hourly scheduling and bounded diagnosis sandbox. All fixtures and equipment assumptions are illustrative.",
    )


def catalogue():
    doc = copy.deepcopy(_catalogue())
    for topic, page in doc["topics"].items():
        page["evidence"] = evidence_claims(topic)
    return doc


def snapshot():
    return catalogue()


def default_examples():
    saved = json.loads(LOADED_FILES.get("docs/model-examples.json", b"{}"))
    current = bindings()
    return {
        key: copy.deepcopy(item["result"])
        for key, item in saved.items()
        if key in current and item.get("binding") == current[key]
    }


_SAVED_PRICES = object()


def read(
    result,
    topic,
    context="Current model",
    controller=None,
    hour=0,
    prices=None,
    *,
    service_prices=_SAVED_PRICES,
):
    if topic not in TOPICS:
        raise ValueError("Unknown documentation topic")
    if context not in ("Current model", "This run", "Learning example"):
        raise ValueError("Unknown documentation context")
    doc = result.get("documentation") if context == "This run" else catalogue()
    page = doc.get("topics", {}).get(topic) if doc else None
    answer = {
        "topic": topic,
        "context": context,
        "run_id": result["run_id"],
        "page": copy.deepcopy(page),
        "source": doc.get("source") if doc else None,
        "status": "available" if page else "unavailable",
        "note": None
        if page
        else "This archive has no original documentation snapshot. Its recorded values remain available; switch explicitly to Current model for current explanations.",
    }
    if context == "This run":
        answer["recorded"] = recorded(
            result, topic, controller, hour, prices, service_prices=service_prices
        )
    return answer


def recorded(result, topic, controller, hour, prices=None, *, service_prices=_SAVED_PRICES):
    if controller not in result["records"] or not 0 <= hour < len(result["records"][controller]):
        raise ValueError("Recorded interval unavailable")
    row = result["records"][controller][hour]
    d = row["decision"]
    info = {
        "controller": controller,
        "interval": hour,
        "time": row["time"],
        "source": result.get("provenance", {}).get("source", {}).get("content_hash"),
        "observations": row["observations_after"],
        "estimated_before": d.get("estimated_state", d.get("state")),
        "requested": row["requested"],
        "applied": row["applied"],
        "original_decision_cost_version": result.get("decision_cost_version"),
        "forecast": d.get("forecast"),
        "solver": d["plan"]["solver"],
        "evidence": d.get("evidence"),
        "note": "Observations are sensor channels; execution records are retrospective model calculations. Neither is empirical plant validation.",
    }
    info["calculation"] = calculation(
        result, topic, controller, hour, prices, service_prices=service_prices
    )
    return copy.deepcopy(info)


def calculation(result, topic, controller, hour, prices=None, *, service_prices=_SAVED_PRICES):
    """Read a topic calculation without copying the inspector's shared context.

    Returned structures may reference the original recording; consumers render
    them read-only. The public inspector still returns an isolated deep copy.
    """
    from methane.battery_trace import trace as battery_trace
    from methane.lineage import derived, economic, trace

    if controller not in result["records"] or not 0 <= hour < len(result["records"][controller]):
        raise ValueError("Recorded interval unavailable")
    row = result["records"][controller][hour]
    d = row["decision"]
    if topic == "battery":
        value = battery_trace(result, controller, hour)
    elif topic in ("solar", "electrolyser", "hydrogen", "co2", "reactor"):
        value = trace(result, controller, hour, topic)
    elif topic == "economics":
        value = economic(
            result,
            controller,
            hour + 1,
            Costs(**prices) if prices else None,
            **({} if service_prices is _SAVED_PRICES else {"service_economics": service_prices}),
        )
    elif topic == "experiments":
        value = derived(result, controller, hour + 1)
    elif topic == "diagnosis":
        value = {
            "observed": row["observations_after"],
            "diagnosis_before": d.get("diagnosis"),
            "diagnosis_after": row["diagnosis_after"],
        }
    elif topic == "weather":
        value = d.get("forecast", d.get("evidence", {}).get("solar", {}))
    elif topic in (
        "cleaning",
        "inspection",
        "recovery",
        "charging",
        "logistics",
        "service_costs",
        "service_uncertainty",
    ):
        field = row.get("field_operations") or {}
        state = field.get("state", {})
        decision = field.get("decision", {})
        value = {
            "original_policy": d.get("policy"),
            "recorded_path": f"/records/{controller}/{hour}/field_operations",
            "scope": "Original recorded service work, observations, plans and resources. Absent fields were not recorded; no current fixture is substituted.",
        }
        fields = {
            "cleaning": (
                "surface_events",
                "soiling_before",
                "soiling_after",
                "soiling_loss_kw",
                "available_pv_kw",
                "unserviced_pv_kw",
                "robot_use_kwh",
            ),
            "inspection": ("fixed_service_kwh", "mission_events"),
            "charging": (
                "energy_before_kwh",
                "charge_input_kwh",
                "charging_loss_kwh",
                "robot_use_kwh",
                "energy_after_kwh",
                "requested_service_kwh",
                "applied_service_kwh",
            ),
            "logistics": (
                "resource_events",
                "support_effects",
                "human_hours",
                "human_visits",
                "remote_hours",
            ),
        }.get(topic, ())
        value["operands"] = {k: field.get(k) for k in fields}
        if topic == "cleaning":
            value["surface"] = state.get("surface")
        elif topic == "inspection":
            value["available_inspection"] = decision.get("inspection")
        elif topic == "logistics":
            value["orders"] = state.get("orders")
            value["support"] = state.get("support")
        elif topic == "service_uncertainty":
            value["observed_beliefs"] = decision.get("uncertainty_beliefs")
        elif topic == "recovery":
            recovery = d.get("recovery_planning") or {}
            value["recovery"] = {
                k: recovery.get(k)
                for k in (
                    "version",
                    "status",
                    "request",
                    "test_appointment",
                    "recovery_obligation",
                    "verification_loop",
                    "commitment_changes",
                    "due_hour",
                    "next_eligible_hour",
                    "reason",
                )
            }
            value["service_obligations"] = (d.get("service_control") or {}).get("obligations")
            value["mission_events"] = field.get("mission_events")
        if topic == "service_costs" and result["config"].get("service_economics"):
            from methane.service_economics import report

            value["calculation_source"] = LOADED_SOURCE["content_hash"]
            value["price_basis"] = (
                "Original recorded service assumptions, recalculated with the identified report implementation"
            )
            value["cost_calculation"] = report(
                result["records"][controller][: hour + 1], result["config"]["service_economics"]
            )
    elif topic == "controllers":
        value = {
            "policy": d["policy"],
            "estimated_state": d.get("estimated_state"),
            "forecast": d.get("forecast"),
            "predicted": d["plan"].get("predicted"),
            "trajectory": d["plan"]["trajectory"],
            "evidence": d.get("evidence"),
        }
    else:
        value = {
            "pv_kw": row["pv_kw"],
            "demand_kw": row["demand_kw"],
            "curtailed_kwh": row["curtailed_kwh"],
            "balance_residual_kwh": row["electrical_residual_kwh"],
            "battery": row["state"]["battery_kwh"],
            "audits": row.get("audits", []),
        }
    return value


def reference_html(doc):
    esc = html.escape
    if not doc:
        return "<p>Original explanations unavailable for this archive. No current documentation is substituted.</p>"
    pages = []
    for key, t in doc["topics"].items():
        body = "".join(
            "<h3>"
            + esc(p["title"])
            + "</h3><p>"
            + esc(p["text"])
            + '</p><p class="equation">'
            + esc(p["equation"])
            + "</p>"
            for p in t["passages"]
        )
        assumptions = "".join("<li>" + esc(a["text"]) + "</li>" for a in t["assumptions"])
        references = "".join(
            '<li><a href="' + esc(u, quote=True) + '">' + esc(u) + "</a></li>"
            for u in t["sources"]
            if u.startswith("https://")
        )
        evidence = "".join(
            "<li>" + esc(c["claim"] + ": " + c["status"] + " — " + c.get("scope", "")) + "</li>"
            for c in t["evidence"]
        )
        pages.append(
            f'<section id="{key}"><h2>{esc(t["title"])}</h2><p>{esc(t["purpose"])}</p>{body}<h3>Assumptions</h3><ul>{assumptions}</ul><h3>Evidence</h3><ul>{evidence}</ul><ul>{references}</ul></section>'
        )
    return "".join(pages)


def offline_report(result):
    from methane.learning import evaluate

    esc = html.escape
    doc = result.get("documentation")
    examples = result.get("learning_examples", {})
    # Only calculate with a matching execution source. Never run current kernels
    # under an archived identity, even if the topic names match.
    if not examples and doc and doc.get("source") == LOADED_SOURCE["content_hash"]:
        examples = {k: evaluate(k) for k in TOPICS}

    def rows_html(items):
        return (
            "<table><tbody>"
            + "".join(
                "<tr><td>" + esc(str(k)) + "</td><td>" + esc(str(v)) + "</td></tr>"
                for k, v in items
            )
            + "</tbody></table>"
        )

    example_html = "".join(
        "<section><h3>"
        + esc(k)
        + " · saved learning output</h3><p>"
        + esc(v.get("summary", ""))
        + "</p>"
        + rows_html((m["label"], str(m["value"]) + " " + m["unit"]) for m in v.get("metrics", []))
        + "<details><summary>Saved inputs, trajectories and checks</summary><pre>"
        + esc(json.dumps(v, indent=2))
        + "</pre></details></section>"
        for k, v in examples.items()
    )
    rows = []

    def operands(value, prefix=""):
        if isinstance(value, dict):
            for key, item in value.items():
                yield from operands(item, prefix + " / " + key if prefix else key)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                yield from operands(item, f"{prefix} / {i}")
        else:
            yield prefix, "Undefined" if value is None else value

    for name, rs in result["records"].items():
        for i, r in enumerate(rs):
            calculations = {k: recorded(result, k, name, i) for k in TOPICS}
            detail = []
            for component, calculation in calculations.items():
                trace = calculation.get("calculation") or {}
                nodes = trace.get("nodes") or trace.get("report", {}).get("lineage", {}).get(
                    "nodes", []
                )
                # Keep all predicted actions and states readable without duplicating
                # component kernel records already preserved in recorded-run.json.gz.
                if component == "controllers":
                    trace = {
                        **trace,
                        "trajectory": [
                            {"offset": j, "applied": step["applied"], "ending": step["state"]}
                            for j, step in enumerate(trace.get("trajectory", []))
                        ],
                    }
                detail.append(
                    "<h3>"
                    + esc(component)
                    + "</h3>"
                    + rows_html(
                        (
                            n.get("label", n["id"]),
                            str(n["value"])
                            + " "
                            + n.get("unit", "")
                            + " · "
                            + str(n.get("formula") or "")
                            + " · "
                            + str(n.get("source", "")),
                        )
                        for n in nodes
                    )
                    + ("" if nodes else rows_html(operands(trace)))
                )
            rows.append(
                "<details><summary>"
                + esc(f"{name} · interval {i} · {r['time']}")
                + "</summary>"
                + "".join(detail)
                + "<p>Original source: "
                + esc(str(calculations["battery"]["source"]))
                + "</p><p>Original dispatch prices: "
                + esc(str(calculations["battery"]["original_decision_cost_version"]))
                + "</p><p>Cost report implementation: "
                + esc(str(calculations["economics"]["calculation"]["report_source_content_hash"]))
                + "</p><p>Observed sensor channels, decision-time estimates and predicted plans are separately labelled. Component execution operands are retrospective simulator calculations.</p>"
                + "</details>"
            )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dispatch Lab — saved model report</title><style>body{background:#222;color:#ffc475;font:16px/1.7 monospace;max-width:76ch;margin:3rem auto;padding:0 1.5rem}a{color:inherit}section{padding:2rem 0;border-top:1px solid #77532f}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.equation{padding:1rem;border:1px solid #77532f}table{width:100%;border-collapse:collapse;font-size:13px}td{padding:8px;border-bottom:1px solid #77532f}</style><h1>Saved model report</h1><p>Run '
        + esc(result["run_id"])
        + "</p><p>Read-only snapshot. Live learning calculations require the restored application. Recorded playback and numerical recomputation are distinct.</p>"
        + reference_html(doc)
        + "<h2>Saved example outputs</h2>"
        + example_html
        + (
            "<h2>Field operations / saved model and records</h2><p>Service state is recorded separately from process state. Repair outcomes below are retrospective; work completion does not establish diagnostic recovery.</p><pre>"
            + esc(json.dumps(result["field_operations_model"], indent=2))
            + "</pre>"
            + "".join(
                "<details><summary>"
                + esc(name)
                + " / service records</summary><pre>"
                + esc(
                    json.dumps(
                        [
                            {"hour": r["hour"], **r["field_operations"]}
                            for r in rs
                            if "field_operations" in r
                        ],
                        indent=2,
                    )
                )
                + "</pre></details>"
                for name, rs in result["records"].items()
            )
            if result.get("field_operations_model")
            and result["config"].get("field_operations", {}).get("enabled")
            else ""
        )
        + "<h2>Recorded calculations</h2>"
        + "".join(rows)
        + "</html>"
    )


def collect_evidence():
    import xml.etree.ElementTree as ET

    directory = ROOT / "build/model"
    stamp = json.loads((directory / "source-under-test.json").read_text())
    suites = ET.parse(directory / "pytest.xml").getroot()
    relevant = {
        "battery": ["battery_independent"],
        "solar": ["solar"],
        "electrolyser": ["independent_gas"],
        "hydrogen": ["independent_gas"],
        "co2": ["independent_gas"],
        "reactor": ["independent_thermal"],
        "weather": ["forecast_availability"],
        "diagnosis": [
            "diagnosis_cases",
            "ambiguity_at_minimum",
            "independent_hold_invariant",
            "unambiguous_evidence",
        ],
        "economics": ["repricing_keeps"],
        "controllers": ["comparison_boundaries"],
        "experiments": ["comparison_boundaries"],
        "bus": [],
    }
    topics = {}
    examples = default_examples()
    for topic in TOPICS:
        cases = [
            c
            for c in suites.iter("testcase")
            if c.get("name", "").endswith("[" + topic + "]")
            or any(token in c.get("name", "") for token in relevant.get(topic, []))
        ]
        topics[topic] = {
            "status": "missing"
            if not cases or all(c.find("skipped") is not None for c in cases)
            else "failed"
            if any(c.find("failure") is not None or c.find("error") is not None for c in cases)
            else "passed",
            "test_cases": [c.get("classname", "") + "::" + c.get("name", "") for c in cases],
            "duration_seconds": sum(float(c.get("time", 0)) for c in cases),
            "fixture_inputs": examples.get(topic, {}).get("inputs"),
            "check_tolerances": list(
                {
                    (a["check_id"], a["tolerance"], a["unit"]): {
                        "check": a["check_id"],
                        "tolerance": a["tolerance"],
                        "unit": a["unit"],
                    }
                    for a in examples.get(topic, {}).get("checks", [])
                    if all(k in a for k in ("check_id", "tolerance", "unit"))
                }.values()
            ),
        }
    report = {
        "schema_version": "dispatch-lab/documentation-evidence/1",
        "source": stamp["source"]["content_hash"],
        "source_matches": stamp["source"]["content_hash"] == LOADED_SOURCE["content_hash"],
        "topics": topics,
        "junit_sha256": hashlib.sha256((directory / "pytest.xml").read_bytes()).hexdigest(),
    }
    (directory / "evidence.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["check", "review", "generate", "examples", "evidence"])
    args = parser.parse_args()
    if args.command == "check":
        check_freshness()
        print("Model documentation bindings are current")
    elif args.command == "evidence":
        print(json.dumps(collect_evidence(), indent=2))
    elif args.command == "examples":
        from methane.learning import evaluate

        current = bindings()
        saved = {key: {"binding": current[key], "result": evaluate(key)} for key in TOPICS}
        if any(x["result"]["status"] != "complete" for x in saved.values()):
            raise ValueError("A default teaching fixture did not complete")
        (ROOT / "docs/model-examples.json").write_text(json.dumps(saved, sort_keys=True) + "\n")
    elif args.command == "review":
        (ROOT / REVIEW).write_text(json.dumps(bindings(), indent=2, sort_keys=True) + "\n")
    else:
        (ROOT / "docs/model-catalogue.json").write_text(
            json.dumps(catalogue(), indent=2, sort_keys=True) + "\n"
        )
