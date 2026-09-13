"""Guarded service predictions over production recipes and resource accounting.

A predicted finding is an explicit condition, never a fabricated Reading. The
result is not an executable mission; current execution must rebuild a recipe
from observations when its decision boundary actually arrives.
"""

import copy
from dataclasses import asdict, dataclass, replace

from methane.services.adapters import claims, eligibility, schedule, work_stages
from methane.services.contracts import MissionPlan, WorkOrder, nonnegative
from methane.services.core import ASSETS
from methane.services.coupling import identity
from methane.services.planning import Commitment
from methane.services.pricing import price
from methane.services.visit_planning import check_journeys

VERSION = "conditional-service-work/1"


@dataclass(frozen=True)
class GuardedWork:
    plan: MissionPlan
    finding_id: str | None
    not_before: float
    guard: dict | None
    interruption_at: float | None = None

    def __post_init__(self):
        self.validate()

    def validate(self):
        nonnegative(self.not_before, "conditional decision boundary")
        if (
            self.plan.starting_at < self.not_before
            or self.plan.order.requested_at < self.plan.context.at_hour
        ):
            raise ValueError("Conditional work precedes its decision information")
        if self.guard is not None:
            g = self.guard
            if self.finding_id != identity(g) or g.get("context") != "prediction":
                raise ValueError("Conditional finding identity mismatch")
            for key in ("measured_at", "available_at"):
                nonnegative(g[key], "predicted finding " + key)
            if (
                not self.plan.context.at_hour
                <= g["measured_at"]
                <= g["available_at"]
                <= self.not_before
            ):
                raise ValueError("Conditional work precedes its predicted finding")
        elif self.finding_id is not None:
            raise ValueError("Missing conditional finding")
        if self.interruption_at is not None:
            nonnegative(self.interruption_at, "predicted interruption time")
            effects = [(b, s) for _, b, s in schedule(self.plan) if s.effect]
            if (
                self.plan.order.action != "read-trip-contact"
                or not self.plan.asset.battery_resource
                or len(effects) != 1
                or self.interruption_at != effects[0][0]
            ):
                raise ValueError(
                    "Only the registered mobile contact-read interruption is supported"
                )

    def demand_plan(self):
        """Use the execution interruption boundary, keeping the full launch recipe.

        The mobile read may fail at perform completion, before sampling. Already
        entered consumables and work remain spent; verification and return do
        not occur. Launch feasibility still reserves the original return route.
        """
        self.validate()
        if self.interruption_at is None:
            return self.plan
        return replace(
            self.plan,
            stages=tuple(
                stage for _, end, stage in schedule(self.plan) if end <= self.interruption_at
            ),
            adapter_id="conditional-interrupted-contact-adapter/1",
        )

    def to_dict(self):
        return dict(
            context="prediction",
            implementation_id=VERSION,
            **asdict(self),
            executable=False,
            scope="Conditional recipe, not a request accepted by execution. Rebuild from actual observations at the future boundary.",
        )


def remedy(runtime, action, *, requested_at, finding=None, request_id="predicted-remedy"):
    """Known module replacement or a reset guarded by a future usable contact.

    Every requirement other than that single explicit finding is checked using
    the original context. Future crew lead starts when the conditional request
    becomes known, not at the earlier inspection decision.
    """
    runtime._require_prepared()
    nonnegative(requested_at, "conditional request time")
    if requested_at < runtime.executive.at_hour:
        raise ValueError("A new remedy cannot be requested before this decision")
    if action not in ("reset", "module-replacement"):
        raise ValueError("No registered conditional remedy for this action")
    actor, face_id = ("reset", "ELY/reset") if action == "reset" else ("crew", "ELY/module")
    if ASSETS[actor] not in runtime.registry.assets or not runtime._available(ASSETS[actor]):
        raise ValueError("Required remedy asset is absent, occupied or awaiting recovery")
    asset = runtime.registry.assets[ASSETS[actor]]
    cap = runtime.registry.capabilities[action]
    face = runtime.registry.interfaces[face_id]
    guard = None
    if finding is not None:
        if finding.get("context") != "prediction" or requested_at < finding["available_at"]:
            raise ValueError("A conditional remedy must await its predicted finding")
        guard = copy.deepcopy(finding)
    if action == "reset":
        if (
            guard is None
            or not guard.get("permitted_contact_reset")
            or guard["finding"] != "closed"
        ):
            raise ValueError("Conditional reset requires a predicted usable closed-contact guard")
        if requested_at - guard["measured_at"] > runtime.options.contact_max_age_hours:
            raise ValueError("The predicted contact would be stale before the reset request")
    start = requested_at + (runtime.options.crew_response_lead_hours if actor == "crew" else 0)
    work = WorkOrder(
        request_id,
        action,
        face_id,
        requested_at,
        "Declared conditional intervention; no physical success or observed finding asserted",
    )
    if action == "reset":
        guarded = tuple(r for r in cap.requirements if r.channel == "trip-contact")
        if len(guarded) != 1 or guarded[0].comparison != "equals" or guarded[0].value is not True:
            raise ValueError("Unsupported reset evidence requirement")
        # Check structure, tools and all known requirements. Keep the actual
        # capability unchanged in the returned recipe, including its unmet guard.
        checked = replace(cap, requirements=tuple(r for r in cap.requirements if r not in guarded))
        reasons = eligibility(work, asset, face, checked, runtime._context)
        if reasons or asset.mobility != "fixed" or asset.home != face.point:
            raise ValueError(
                "; ".join(reasons) or "Conditional reset needs its installed fixed interface"
            )
        plan = MissionPlan(
            work,
            asset,
            face,
            cap,
            start,
            work_stages(asset, face, cap),
            runtime._context,
            "conditional-fixed-service-adapter/1",
        )
    else:
        plan = runtime.registry.build(
            work, asset.asset_id, cap.capability_id, runtime._context, starting_at=start
        )
        plan = replace(plan, adapter_id="conditional-mobile-service-adapter/1")
    if runtime.support:
        plan = runtime.support.decorate(plan)
    return GuardedWork(plan, identity(guard) if guard else None, requested_at, guard)


def project(runtime, work, forecast, prices, *, prefix=(), reference_forecast=None):
    """Resource/cost projection that leaves the live executive and ledger alone."""
    runtime._require_prepared()
    work = tuple(work)
    for item in work:
        item.validate()
    now = runtime.executive.at_hour
    if now != int(now):
        raise ValueError("Conditional process projection requires an hourly decision boundary")
    n = len(forecast["pv_kw"])
    if type(n) is not int or not n or len(forecast["ambient_c"]) != n:
        raise ValueError("A conditional schedule needs complete hourly forecast inputs")
    if forecast.get("decision_hour") != now:
        raise ValueError("The conditional schedule must use the original decision forecast")
    if any(p.plan.context != runtime._context for p in work):
        raise ValueError("Conditional work must retain the original observation context")
    if any(p.plan.starting_at < p.not_before for p in work):
        raise ValueError("Conditional work starts before its information or request boundary")
    if any(p.plan.ending_at > now + n for p in work):
        raise ValueError("New conditional work and return must finish inside this horizon")
    # Read-only feasibility reserves the whole plan, including return margin,
    # against a private copy. No receipt, success or future replenishment enters.
    ledger = copy.deepcopy(runtime.ledger)
    for p in work:
        ledger.reserve(p.plan.order.order_id, *claims(p.plan), now)
    accepted = tuple(
        Commitment(m.plan, m.stage_index, m.entered)
        for m in runtime.executive.missions.values()
        if m.status in ("active", "scheduled")
    )
    visits = tuple(runtime.executive.visits.values())
    grouped = {p.order.order_id for v in visits for p in v.members}
    active_visits = tuple(
        v
        for v in visits
        if any(c.plan.order.order_id in {p.order.order_id for p in v.members} for c in accepted)
    )
    check_journeys(
        [c.plan for c in accepted if c.plan.order.order_id not in grouped] + [p.plan for p in work],
        active_visits,
    )
    interrupted_assets = {w.plan.asset.asset_id for w in work if w.interruption_at is not None}
    if any(sum(w.plan.asset.asset_id == asset for w in work) > 1 for asset in interrupted_assets):
        raise ValueError(
            "A predicted stranded asset cannot undertake later work without observed recovery"
        )
    demand_plans = [p.demand_plan() for p in work]
    additions = tuple(Commitment(p) for p in demand_plans)
    profile = runtime.planned_demands(n, candidates=demand_plans)
    treatment = None
    if runtime.optical is not None:
        from methane.services.coupling import _treatment

        if reference_forecast is None:
            raise ValueError("Optical service coupling requires its original radiation forecast")
        forecast, treatment = _treatment(runtime, forecast, reference_forecast, demand_plans)
    elif reference_forecast is not None:
        raise ValueError("A radiation treatment reference needs the section optical model")
    standby = profile["standby_kw"]
    if abs(max(0, forecast["pv_kw"][0] - standby) - runtime._available_service_pv) > 1e-8:
        raise ValueError("Current power differs from the original prepared service context")
    for row, pv in zip(profile["rows"], forecast["pv_kw"], strict=True):
        if row["bus_peak_kw"] - standby > max(0, pv - standby) + 1e-9:
            raise ValueError("Conditional tool peak exceeds forecast solar supply")
    quote = price(
        accepted,
        additions,
        prices,
        at_hour=int(now),
        hours=n,
        installed=[k for k, v in runtime.interval["assets"].items() if v],
        prefix=prefix,
        visits=tuple(runtime.executive.visits.values()),
    )
    if interrupted_assets:
        profile["scope"] = (
            "Conditional demand through each declared interruption boundary. Entered materials "
            "and elapsed work remain spent; interrupted verification/return do not occur. "
            "Other accepted work keeps its original continuation assumption. Stranding and "
            "outstanding recovery are reported separately, not treated as completed return."
        )
        quote["scope"] = (
            "Conditional costs through declared interruptions and other projected work. "
            "No unperformed verification or return activity is charged. Future retrieval "
            "remains an outstanding obligation with no invented schedule or price credit. "
            "Accumulated usage/parts pools retain their existing economic treatment."
        )
    result_forecast = copy.deepcopy(forecast)
    result_forecast["service_kw"] = [r["bus_kwh"] for r in profile["rows"]]
    isolation = forecast.get("electrolyser_isolated", [False] * n)
    if len(isolation) != n or any(type(x) is not bool for x in isolation):
        raise ValueError("Original isolation needs one Boolean per interval")
    result_forecast["electrolyser_isolated"] = [
        x or r["electrolyser_isolated"] for x, r in zip(isolation, profile["rows"], strict=True)
    ]
    out = dict(
        implementation_id=VERSION,
        context="prediction",
        work=[w.to_dict() for w in work],
        projection=profile,
        predicted_interruptions=[
            dict(
                order_id=w.plan.order.order_id,
                asset_id=w.plan.asset.asset_id,
                at_hour=w.interruption_at,
                location=w.plan.interface.point,
                status="stranded",
                return_completed=False,
                observation_produced=False,
                outstanding_work="Retrieve or otherwise recover the asset, then verify readiness",
                demand_plan=w.demand_plan().to_dict(),
            )
            for w in work
            if w.interruption_at is not None
        ],
        treatment=treatment,
        service_pricing=quote,
        forecast=result_forecast,
        scope="Conditional demands and known prices only. No restoration, observation arrival or accepted future supply is inferred from procedure completion.",
    )
    out["projection_id"] = identity(out)
    return out
