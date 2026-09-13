"""Explicit repeated-computation editions over the matched field-study contracts."""

import copy
import math

from methane.provenance import digest

RESOLVER = "repeated-field-computation/1"
REPORTING = "field-computation-qualification/1"


def require_dc_basis(config):
    if config.solar or (
        config.field_operations.enabled
        and config.service_system is not None
        and config.service_system.cleaning_model == "section-optical/1"
    ):
        raise ValueError(
            "This constant-DC computation fixture requires a plant without an explicit solar "
            "conversion design or optical section model. Use its reference basis, or a separately "
            "declared weather/conversion protocol; the selected plant is not changed."
        )


def settings(spec, tier):
    value = spec["tiers"][tier]["computation"]
    if set(value) != {"budgets", "repetitions", "absolute_tolerance"}:
        raise ValueError("Computation settings require budgets, repetitions and absolute tolerance")
    repeats, tolerance = value["repetitions"], value["absolute_tolerance"]
    if type(repeats) is not int or not 2 <= repeats <= 20:
        raise ValueError("Computation qualification requires 2–20 distinct repetitions")
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(tolerance)
        or not 0 < tolerance <= 0.01
    ):
        raise ValueError("Declare a finite positive numerical comparison tolerance up to 0.01")
    from methane.field_studies import unique

    budgets = value["budgets"]
    unique(budgets, "computation budget")
    for budget in budgets:
        if set(budget) != {"id", "process_seconds", "service_seconds", "investigation_seconds"}:
            raise ValueError("Every budget must state the three independent computation limits")
        for key in ("process_seconds", "service_seconds", "investigation_seconds"):
            n = budget[key]
            if (
                isinstance(n, bool)
                or not isinstance(n, (int, float))
                or not math.isfinite(n)
                or not 0 < n <= 120
            ):
                raise ValueError("Computation limits must be finite positive seconds, at most 120")
    return value


def resolve(spec, basis, tier):
    from methane.config import Config
    from methane.field_studies import RESOLVER as FIELD_RESOLVER
    from methane.field_studies import matching_inputs
    from methane.field_studies import resolve as field_resolve
    from methane.policy import Policy
    from methane.studies import differences

    require_dc_basis(Config.from_dict(basis))
    config = settings(spec, tier)
    cases = []
    for budget in config["budgets"]:
        expanded = copy.deepcopy(spec)
        expanded["resolver"] = FIELD_RESOLVER
        expanded["tiers"][tier]["solver_seconds"] = budget["process_seconds"]
        for p in expanded["policies"].values():
            for key, limit in (
                ("service", "service_seconds"),
                ("investigation", "investigation_seconds"),
            ):
                if p.get(key) is None:
                    raise ValueError(
                        "This qualification requires explicit service and investigation policies"
                    )
                p[key]["comparison_seconds"] = budget[limit]
            Policy(**p)
        resolved = field_resolve(expanded, basis, tier)
        for case in resolved:
            require_dc_basis(Config.from_dict(case["config"]))
        # Interleave budgets within each repeat later; no repeat changes its seed.
        for repetition in range(1, config["repetitions"] + 1):
            for original in resolved:
                case = copy.deepcopy(original)
                physical = matching_inputs(case["config"])
                physical["scenario"] = {
                    k: v for k, v in physical["scenario"].items() if k != "solver_seconds"
                }
                numerical = digest(dict(config=case["config"], policies=case["policies"]))
                metadata = dict(
                    budget=budget,
                    repetition=repetition,
                    variant=case["variant"],
                    physical_inputs_hash=digest(physical),
                    numerical_inputs_hash=numerical,
                )
                case.update(
                    computation=metadata,
                    case_id=digest(
                        dict(protocol=digest(spec), original=case["case_id"], repetition=repetition)
                    )[:24],
                    group_id=digest(dict(group=case["group_id"], repetition=repetition))[:24],
                    variant=f"{case['variant']} / {budget['id']} / repeat {repetition}",
                    label=f"{case['label']} · {budget['id']} · repeat {repetition}",
                    changes_from_basis=differences(basis, case["config"]),
                )
                cases.append(case)
    return sorted(
        cases,
        key=lambda c: (
            c["computation"]["repetition"],
            c["condition"],
            c["computation"]["variant"],
            c["seed"],
            [b["id"] for b in config["budgets"]].index(c["computation"]["budget"]["id"]),
            c["arm_id"],
        ),
    )


def weather(config, definition):
    """Declared hourly DC scheduling fixture, not a solar geometry/irradiance test."""
    from methane.weather import synthetic

    require_dc_basis(config)
    if (
        set(definition) != {"version", "pv_fraction", "ambient_c"}
        or definition["version"] != "constant-dc-computation/1"
    ):
        raise ValueError("Unknown computation weather fixture")
    fraction, ambient = definition["pv_fraction"], definition["ambient_c"]
    if (
        any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in (fraction, ambient)
        )
        or not 0 <= fraction <= 1
        or not -40 <= ambient <= 60
    ):
        raise ValueError("Invalid declared DC fraction or ambient temperature")
    result = synthetic(config)
    value = config.plant.solar_kw * fraction
    for mapping in (result["truth"], result["template"]):
        for r in mapping.values():
            r.update(pv_kw=value, irradiance_wm2=fraction * 1000, ambient_c=ambient)
    result["reference"] = (
        f"Declared constant hourly mean DC at {fraction:g} of array nameplate and {ambient:g}°C. Computation fixture; not site weather or a solar geometry comparison."
    )
    result["computation_fixture"] = copy.deepcopy(definition)
    return result


def capture(result, controller, elapsed_seconds):
    """Compact original execution evidence; reporting never solves the plant again."""
    rows = result["records"][controller]
    vectors, work, solvers, selections = [], [], [], []
    for r in rows:
        d = r["decision"]
        vectors.append(
            {
                **{"requested." + k: v for k, v in r["requested"].items()},
                **{"applied." + k: v for k, v in r["applied"].items()},
                **{"state." + k: v for k, v in r["state"].items()},
                **{
                    "diagnosis." + k: v
                    for k, v in r["diagnosis_after"].items()
                    if isinstance(v, (int, float, bool))
                },
            }
        )
        orders = r["field_operations"]["state"]["orders"]
        work.append(
            digest(
                [
                    {
                        k: o.get(k)
                        for k in (
                            "id",
                            "kind",
                            "created_hour",
                            "status",
                            "completed_hour",
                            "verified_at_hour",
                            "followup_of",
                        )
                    }
                    for o in orders
                ]
            )
        )
        solvers.append(copy.deepcopy(d.get("plan", {}).get("solver")))
        service = d.get("service_control") or {}
        selections.append(
            dict(
                hour=r["hour"],
                status=service.get("status"),
                fallback_used=service.get("fallback_used"),
                evaluated_candidates=sum(
                    c.get("status") != "not-evaluated" for c in service.get("candidates", [])
                ),
                not_evaluated_candidates=sum(
                    c.get("status") == "not-evaluated" for c in service.get("candidates", [])
                ),
                omissions=copy.deepcopy(service.get("omitted_candidates")),
                investigation_status=[
                    e["status"] for e in (service.get("investigation") or {}).get("episodes", [])
                ],
            )
        )
    return dict(
        version=REPORTING,
        source=result["provenance"]["source"]["content_hash"],
        weather=result["provenance"]["weather_content_hash"],
        inputs=digest(
            dict(config=result["config"], policies=result["provenance"]["controller_policies"])
        ),
        elapsed_seconds=elapsed_seconds,
        vectors=vectors,
        work=work,
        solvers=solvers,
        selections=selections,
    )


def qualify(value):
    """Retain incomplete repeats and keep numerical stability separate from quality."""
    spec = value["manifest"]["protocol"]
    expected = settings(spec, value["manifest"]["tier"])
    groups = {}
    for case in value["cases"]:
        c = case["computation"]
        key = (case["condition"], c["variant"], case["seed"], case["arm_id"], c["budget"]["id"])
        groups.setdefault(key, []).append(case)
    output = []
    for key, cases in groups.items():
        packets = [c["entry"].get("computation") for c in cases]
        complete = (
            len(cases) == expected["repetitions"]
            and {c["computation"]["repetition"] for c in cases}
            == set(range(1, expected["repetitions"] + 1))
            and all(
                c["entry"]["status"] == "complete"
                and p is not None
                and p.get("version") == REPORTING
                and all(
                    len(p.get(k, [])) == c["config"]["scenario"]["hours"]
                    for k in ("vectors", "work", "solvers", "selections")
                )
                and all(
                    isinstance(n, (int, float)) and math.isfinite(n)
                    for vector in p["vectors"]
                    for n in vector.values()
                )
                for c, p in zip(cases, packets, strict=True)
            )
        )
        operands_match = (
            complete
            and len({(p["inputs"], p["source"], p["weather"]) for p in packets}) == 1
            and all(
                p["inputs"] == c["computation"]["numerical_inputs_hash"]
                and p["source"] == value["manifest"]["source_hash"]
                and p["weather"] == c.get("weather_hash")
                for c, p in zip(cases, packets, strict=True)
            )
        )
        first = None
        max_difference = 0
        work_matches = None
        if operands_match:
            baseline = packets[0]
            for other in packets[1:]:
                if len(baseline["vectors"]) != len(other["vectors"]):
                    complete = False
                    break
                for h, (a, b) in enumerate(zip(baseline["vectors"], other["vectors"], strict=True)):
                    if set(a) != set(b):
                        complete = False
                        break
                    difference = max((abs(float(a[k]) - float(b[k])) for k in a), default=0)
                    max_difference = max(max_difference, difference)
                    if difference > expected["absolute_tolerance"] and (first is None or h < first):
                        first = h
            work_matches = all(p["work"] == baseline["work"] for p in packets)
        quality = [s for p in packets if p for s in p["solvers"] if s]
        gaps = [
            s["gap"]
            for s in quality
            if isinstance(s.get("gap"), (int, float)) and math.isfinite(s["gap"])
        ]
        incomplete_solves = sum(s.get("termination") != "optimal-within-tolerance" for s in quality)

        def extent(metric, cases=cases):
            numbers = [c.get("outcomes", {}).get(metric) for c in cases]
            return (
                [min(numbers), max(numbers)]
                if numbers and all(type(x) in (int, float) and math.isfinite(x) for x in numbers)
                else None
            )

        output.append(
            dict(
                condition=key[0],
                variant=key[1],
                seed=key[2],
                arm_id=key[3],
                budget=key[4],
                case_ids=[c["case_id"] for c in cases],
                expected_repetitions=expected["repetitions"],
                completed_repetitions=sum(c["entry"]["status"] == "complete" for c in cases),
                repeatability="incomplete"
                if not complete
                else "unmatched inputs"
                if not operands_match
                else "stable in sampled repeats"
                if first is None and work_matches
                else "different recorded trajectories",
                first_different_interval=first,
                maximum_numeric_difference=max_difference if operands_match else None,
                work_matches=work_matches,
                methane_range_kg=extent("methane_kg"),
                allocated_range_eur=extent("total_eur"),
                solve_quality="missing"
                if not complete
                or not quality
                or len(quality) != sum(len(p["vectors"]) for p in packets if p)
                else "limited or fallback solves retained"
                if incomplete_solves
                else "all recorded process solves within requested tolerance",
                limited_or_fallback_solves=incomplete_solves,
                maximum_gap=max(gaps) if gaps else None,
                unevaluated_service_candidates=sum(
                    s["not_evaluated_candidates"] for p in packets if p for s in p["selections"]
                ),
                omitted_service_candidates=sum(
                    len(s["omissions"] or []) for p in packets if p for s in p["selections"]
                ),
                execution_seconds=[p["elapsed_seconds"] for p in packets if p],
            )
        )
    return dict(
        version=REPORTING,
        absolute_tolerance=expected["absolute_tolerance"],
        groups=output,
        scope="Repeated executions of identical inputs, not independent random seeds. Stability in a finite sample does not prove optimality or determinism. Process termination is separate from outer service/investigation search completeness; original candidates and exclusions remain in each archive.",
    )


def markdown(value):
    rows = [
        "## Computation qualification",
        "",
        value["scope"],
        "",
        "| Condition / plant / seed | Arm / budget | Repeatability | Methane range / kg | Process solve quality | Largest recorded gap |",
        "|---|---|---|---|---|---|",
    ]
    for g in value["groups"]:
        numbers = " to ".join(f"{v:.6f}" for v in g["methane_range_kg"] or []) or "Undefined"
        gap = "Missing" if g["maximum_gap"] is None else f"{g['maximum_gap']:.6f}"
        rows.append(
            f"| {g['condition']} / {g['variant']} / {g['seed']} | {g['arm_id']} / {g['budget']} | {g['repeatability']} | {numbers} | {g['solve_quality']} | {gap} |"
        )
    return "\n".join(rows) + "\n"
