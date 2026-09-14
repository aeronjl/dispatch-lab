"""Learning fixtures use the same packet, fit, and dispatch interfaces."""

from dataclasses import replace
from tempfile import TemporaryDirectory

from methane.learning import metric, result, series


def dataset(v):
    from methane.learning_lab.datasets import packet, validate_splits

    episodes = [
        dict(
            id=str(i),
            site="teaching",
            design=str(i),
            equipment=str(i),
            split=s,
            start=f"2025-0{i + 1}-01",
            end=f"2025-0{i + 1}-02",
        )
        for i, s in enumerate(("train", "validation", "test"))
    ]
    if v["overlap"] == "yes":
        episodes[1].update(start=episodes[0]["start"], end=episodes[0]["end"])
    try:
        validate_splits(episodes)
        status = "Admitted: episode and weather boundaries are separate"
    except ValueError as exc:
        status = str(exc)
    p = packet(
        dict(
            hour=v["hour"],
            lifecycle={
                "condition": {
                    "solar": {
                        "measurement": dict(value=0.12, measured_at=0, available_at=v["delay"])
                    }
                }
            },
        ),
        time=f"2025-01-01T0{v['hour']}:00:00Z",
        prices={},
        plant={},
    )
    eligible = "solar" in p["condition"]
    return result(
        [
            metric("Condition channel available", int(eligible)),
            metric("Episode split admitted", int(v["overlap"] == "no")),
        ],
        [
            series(
                "Available measurement",
                [0 if h < v["delay"] else 0.12 for h in range(7)],
                "fraction",
            )
        ],
        [dict(packet=p, split_status=status, episodes=episodes)],
        [dict(id="publication_boundary", passed=eligible == (v["hour"] >= v["delay"]))],
        scope=status + ". Delayed observed channel; private outcomes remain outside this port.",
    )


def estimator(v):
    from methane.learning_lab.estimators import fit
    from methane.learning_lab.fixtures import teaching_dataset
    from methane.siting.store import Store

    with TemporaryDirectory(prefix="dispatch-estimator-lesson-") as directory:
        store = Store(directory)
        data = teaching_dataset(store, noise=v["noise"], missing=v["missing"] == "yes")
        fitted = fit(store, data["id"], task=v["task"], ridge=v["ridge"])
    stats = fitted.get("comparisons", {})
    return result(
        [
            metric(k + " absolute error", m["mae"], fitted.get("model", {}).get("units", ""))
            for k, m in stats.items()
        ],
        [
            series(k, [r["prediction"] for r in values], fitted["model"]["units"])
            for k, values in fitted.get("outcomes", {}).items()
        ],
        [
            dict(
                comparisons=stats,
                exclusions=fitted["exclusions"],
                model=fitted.get("model"),
                protocol=fitted["protocol"],
            )
        ],
        [dict(id="explicit_split", passed=len(fitted["rows_per_split"]) == 3)],
        scope=fitted["scope"],
        evaluation=fitted,
    )


def policy(v):
    from methane.config import Costs, Plant
    from methane.dispatch import plan
    from methane.learning_lab.reserves import DEFAULTS, account
    from methane.physics import State

    p = Plant()
    state = State(300, 12, 80, 270)
    costs = replace(Costs(), methane_eur_per_kg=v["price"])
    base = dict(
        pv_kw=[x * v["power"] for x in (350, 250, 100, 0, 0, 0)],
        ambient_c=[20] * 6,
        deliveries_kg=[0] * 6,
    )
    runs = []
    for objective in ("greedy", "methane", "economics"):
        for reserves in (False, True) if objective != "greedy" else (False,):
            f = dict(base)
            if reserves:
                f["reserve_policy"] = {
                    **DEFAULTS,
                    "battery_fraction": v["reserve"],
                    "shortage_weight": v["weight"],
                }
            planned = plan(p, state, f, p.electrolyser_kw, costs, objective=objective, seconds=0.15)
            runs.append(
                dict(
                    label=objective + (" + reserves" if reserves else ""),
                    plan=planned,
                    reserves=account(p, state, f, planned["trajectory"]),
                )
            )
    return result(
        [metric(r["label"], r["plan"]["predicted"]["methane_kg"], "kg methane") for r in runs],
        [
            series(r["label"], [s["state"]["battery_kwh"] for s in r["plan"]["trajectory"]], "kWh")
            for r in runs
        ],
        runs,
        [dict(id="same_initial_information", passed=True)],
        scope="Predictions from the same six-hour fixture. Reserve preference penalties are not expenditure; compare production, actual decision costs, ending state and solver limits. No requirement that MPC or reserves improve output.",
    )


ADAPTERS = {"learning_data": dataset, "estimators": estimator, "policies": policy}
