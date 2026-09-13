"""Declared finite search, Pareto comparisons and uncertainty without invented probabilities."""

import copy
import itertools
import math

from methane.config import Config
from methane.siting.contracts import DeploymentDesign
from methane.siting.production import create, inspect
from methane.siting.store import digest

SIZES = {
    "solar_kw",
    "battery_kwh",
    "battery_c_rate",
    "electrolyser_kw",
    "h2_capacity_kg",
    "co2_capacity_kg",
    "methane_max_kgph",
}


def search(
    store,
    *,
    design_ids,
    environment_ids,
    sizes,
    controllers,
    seeds,
    repetitions=1,
    role="design",
    budget=48,
    name="Bounded design search",
):
    if set(sizes) - SIZES or not 1 <= budget <= 96 or not 1 <= repetitions <= 5:
        raise ValueError("Unsupported design axis, budget or repetitions")
    if not design_ids or not environment_ids or not controllers or not seeds:
        raise ValueError("Declare designs, environments, controllers and seeds")
    if any(not values or len(values) > 6 for values in sizes.values()):
        raise ValueError("Each sizing axis needs 1–6 explicit candidates")
    variants = list(itertools.product(*(sizes[k] for k in sorted(sizes)))) or [()]
    if (
        len(variants)
        * len(design_ids)
        * len(environment_ids)
        * len(controllers)
        * len(seeds)
        * repetitions
        > 5000
    ):
        raise ValueError("Screening universe exceeds 5,000 combinations; narrow the declaration")
    cases, excluded, universe = [], [], []
    for did, variant, eid in itertools.product(design_ids, variants, environment_ids):
        base = store.get("design", did)
        env = store.get("environment", eid)
        if base["site_revision"] != env["site_revision"]:
            continue
        settings = dict(zip(sorted(sizes), variant, strict=True))
        candidate = dict(base_design_id=did, environment_id=eid, settings=settings)
        universe.append(candidate)
        try:
            changed = copy.deepcopy(base)
            changed["parent_id"] = did
            changed["name"] = (
                base["name"] + " / " + ", ".join(f"{k}={v}" for k, v in settings.items())
                if settings
                else base["name"]
            )
            changed["config"]["plant"].update(settings)
            solar = changed["config"].get("solar")
            if solar and "solar_kw" in settings:
                total = sum(s["capacity_kw"] for s in solar["sections"])
                for section in solar["sections"]:
                    section["capacity_kw"] *= settings["solar_kw"] / total
            c = Config.from_dict(changed["config"])
            if base.get("assessment_id"):
                a = store.get("assessment", base["assessment_id"])
                limit = a.get("coarse_pv_capacity_kw")
                if limit is not None and c.plant.solar_kw > limit:
                    raise ValueError("PV capacity exceeds saved coarse usable-area screening rule")
            new_id = store.put("design", DeploymentDesign(**changed))
            for controller, seed, rep in itertools.product(
                controllers, seeds, range(1, repetitions + 1)
            ):
                if len(cases) >= budget:
                    excluded.append(
                        {
                            **candidate,
                            "reason": "Declared execution budget exhausted; unevaluated, not physically rejected",
                        }
                    )
                    continue
                cases.append(
                    dict(
                        design_id=new_id,
                        environment_id=eid,
                        controller=controller,
                        seed=seed,
                        repetition=rep,
                        role=role,
                        label=changed["name"],
                    )
                )
        except ValueError as exc:
            excluded.append({**candidate, "reason": str(exc)})
    if not cases:
        raise ValueError("No valid cases in the declared universe")
    protocol = dict(
        schema_version="site-search-universe/1",
        axes=sizes,
        universe=universe,
        exclusions=excluded,
        execution_budget=budget,
        enumeration="Input design order, sorted sizing axes, explicit values, environment/controller/seed/repetition order; no claim of global optimum",
        selection_role=role,
    )
    return create(
        store,
        name=name,
        cases=cases,
        search=protocol,
        purpose="Finite site/plant/service co-design; validate shortlisted designs on held-out chronological years",
    )


def dominates(a, b):
    return (
        a["cost"] <= b["cost"]
        and a["output"] >= b["output"]
        and (a["cost"] < b["cost"] or a["output"] > b["output"])
    )


def weighted_quantile(values, probability):
    ordered = sorted(values)
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= probability - 1e-12:
            return value
    return ordered[-1][0]


def recommend(
    store,
    study_ids,
    *,
    title="Candidate comparison",
    conclusion="",
    cashflow_ids=(),
    probability_weights=None,
    probability_evidence_id=None,
):
    studies = [inspect(store, k) for k in study_ids]
    cash = {
        (v["study_id"], v["case_id"]): v for v in (store.get("cashflow", k) for k in cashflow_ids)
    }
    candidates = []
    for study in studies:
        for case in study["cases"]:
            summary = case["summary"]
            design = store.get("design", case["design_id"])
            site = store.get("site", design["site_revision"])
            assessed = (
                store.get("assessment", design["assessment_id"])
                if design.get("assessment_id")
                else None
            )
            financial = cash.get((study["id"], case["case_id"]))
            c = case["config"]
            # Weather coordinates are excluded only from the matched hardware signature.
            same_plant = {k: v for k, v in c.items() if k not in ("weather", "scenario")}
            candidates.append(
                dict(
                    id=study["id"] + "/" + case["case_id"],
                    study_id=study["id"],
                    case_id=case["case_id"],
                    label=case["label"],
                    site=site["name"],
                    design_id=case["design_id"],
                    environment_id=case["environment_id"],
                    period={
                        k: store.get("environment", case["environment_id"])[k]
                        for k in ("start", "end")
                    },
                    role=case["role"],
                    seed=c["scenario"]["seed"],
                    repetition=case["repetition"],
                    controller=case["controller"],
                    same_plant_group=digest(same_plant),
                    hours=case["hours"],
                    completed_hours=case["completed_hours"],
                    status="complete" if summary else study["state"]["status"],
                    summary=summary,
                    financial=financial,
                    unresolved=(assessed or {}).get("unresolved", ["Parcel assessment absent"]),
                    feasibility_status=(assessed or {}).get("status", "unresolved"),
                    source=study["manifest"]["source"]["content_hash"],
                )
            )
    # Pareto groups share period length and controller. Cross-climate variation remains visible.
    complete = [
        v for v in candidates if v["summary"] and v["summary"].get("methane_kg") is not None
    ]
    for c in complete:
        c["output"] = c["summary"]["methane_kg"]
        c["cost"] = c["summary"]["total_eur"]
        peers = [
            v
            for v in complete
            if v["hours"] == c["hours"]
            and v["controller"] == c["controller"]
            and v["summary"]["total_eur"] is not None
        ]
        c["pareto_within_duration_controller"] = c["cost"] is not None and not any(
            dominates(dict(output=v["summary"]["methane_kg"], cost=v["summary"]["total_eur"]), c)
            for v in peers
        )
    groups = {}
    for c in complete:
        key = digest(
            dict(
                design=c["design_id"], controller=c["controller"], hours=c["hours"], role=c["role"]
            )
        )
        groups.setdefault(key, []).append(c)
    ranges = [
        dict(
            group=k,
            cases=[c["id"] for c in v],
            output_min_kg=min(c["output"] for c in v),
            output_max_kg=max(c["output"] for c in v),
            sample_count=len(v),
            scope="Unweighted scenario/numerical range, not a probability interval",
        )
        for k, v in groups.items()
    ]
    probabilities = None
    if probability_weights is not None:
        if not probability_evidence_id:
            raise ValueError("Probability claims require an explicit supporting evidence record")
        evidence = store.get("evidence", probability_evidence_id)
        if evidence["status"] not in ("reported", "measured") or not evidence["source_id"]:
            raise ValueError("Assumed scenarios do not establish probability support")
        if (
            set(probability_weights) != {c["id"] for c in complete}
            or len({c["hours"] for c in complete}) != 1
            or any(not math.isfinite(w) or w < 0 for w in probability_weights.values())
            or len({(c["design_id"], c["controller"], c["role"]) for c in complete}) != 1
            or len({(c["environment_id"], c["seed"]) for c in complete}) != len(complete)
            or len(complete) != len(candidates)
            or abs(sum(probability_weights.values()) - 1) > 1e-8
        ):
            raise ValueError(
                "Probability weights must cover one complete design/controller/role/duration, exclude numerical repeats, and sum to one"
            )
        values = [(c["output"], probability_weights[c["id"]]) for c in complete]
        probabilities = dict(
            p50_kg=weighted_quantile(values, 0.5),
            p90_exceedance_kg=weighted_quantile(values, 0.1),
            evidence_id=probability_evidence_id,
            weights=probability_weights,
            sample_count=len(values),
            scope="User-supported weighted output distribution; P90 is the lower tenth percentile, not a guarantee. Do not count numerical repetitions as new weather draws.",
        )
    # Rank reversals are paired by environment and design/controller, never inferred from unmatched hours.
    rankings = {}
    for c in complete:
        key = (c["environment_id"], c["hours"])
        rankings.setdefault(key, []).append(c)
    orders = []
    for (environment, hours), items in rankings.items():
        orders.append(
            dict(
                environment_id=environment,
                hours=hours,
                descending_methane=[
                    v["design_id"] + "/" + v["controller"]
                    for v in sorted(items, key=lambda c: c["output"], reverse=True)
                ],
            )
        )
    reversals = []
    for a, b in itertools.combinations(orders, 2):
        if a["hours"] != b["hours"]:
            continue
        common = set(a["descending_methane"]) & set(b["descending_methane"])
        for x, y in itertools.combinations(sorted(common), 2):
            # Establish strict signs from every recorded repeat, not arbitrary tie ordering.
            av = {
                k: [
                    c["output"]
                    for c in complete
                    if c["environment_id"] == a["environment_id"]
                    and c["design_id"] + "/" + c["controller"] == k
                ]
                for k in (x, y)
            }
            bv = {
                k: [
                    c["output"]
                    for c in complete
                    if c["environment_id"] == b["environment_id"]
                    and c["design_id"] + "/" + c["controller"] == k
                ]
                for k in (x, y)
            }
            if (min(av[x]) > max(av[y]) and max(bv[x]) < min(bv[y])) or (
                max(av[x]) < min(av[y]) and min(bv[x]) > max(bv[y])
            ):
                reversals.append(
                    dict(
                        candidates=[x, y],
                        environments=[a["environment_id"], b["environment_id"]],
                        hours=a["hours"],
                    )
                )
    overlaps = []
    for a in candidates:
        if a["role"] != "held-out":
            continue
        for b in candidates:
            if b["role"] == "design" and max(a["period"]["start"], b["period"]["start"]) < min(
                a["period"]["end"], b["period"]["end"]
            ):
                overlaps.append(
                    dict(
                        held_out=a["id"],
                        design_case=b["id"],
                        reason="Calendar overlap with a design-selection period; not independent temporal validation",
                    )
                )
    result = dict(
        schema_version="site-recommendations/1",
        title=title,
        authored_conclusion=conclusion,
        study_ids=study_ids,
        cashflow_ids=list(cashflow_ids),
        candidates=candidates,
        declared_cases=len(candidates),
        completed_cases=len(complete),
        ranges=ranges,
        probabilities=probabilities,
        rankings=orders,
        ranking_order_changed=bool(reversals),
        paired_ranking_reversals=reversals,
        held_out_overlap=overlaps,
        held_out_validation="overlap detected"
        if overlaps
        else "No declared temporal overlap; this does not establish unrecorded selection independence",
        no_build=dict(
            output_kg=0,
            initial_cash_eur=0,
            npv_eur=0,
            scope="No new project; no assumed alternative land income",
        ),
        investment_winners=[
            c["id"]
            for c in complete
            if c["financial"]
            and c["financial"]["npv_eur"] is not None
            and c["financial"]["npv_eur"] > 0
        ],
        boundaries=[
            "Comparison of recorded model outcomes, not a development recommendation",
            "Pareto screen uses allocated period cost and methane, grouped by duration/controller",
            "No-build NPV comparison is available only for complete, explicitly priced scenarios",
            "Identical plants and resized plants have separate signatures",
            "Held-out roles are explicit; inspect year overlap before interpreting generalisation",
            "Missing and unsuccessful attempts remain in the declared denominator",
            "An ordering difference across different candidate universes is not an established paired ranking reversal",
        ],
    )
    return {"id": store.put("recommendation", result), **result}
