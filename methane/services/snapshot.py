"""Recorded service information exposed through a planning-only adapter.

The snapshot is taken after observation/request preparation and before selection.
No effect port, fault state, random variate or later weather is serialised. Plans
are data under known contracts; loading a snapshot never executes captured code.
"""

import copy
from dataclasses import asdict
from types import SimpleNamespace

from methane.config import Plant, WeatherConfig
from methane.field_operations import FieldOperations
from methane.services import SOURCE_IDENTITY
from methane.services.access import Access, Edge
from methane.services.configuration import ServiceSystem
from methane.services.contracts import (
    Asset,
    Capability,
    Context,
    Interface,
    MissionPlan,
    Quantity,
    Reading,
    Requirement,
    Source,
    Stage,
    WorkOrder,
)
from methane.services.coupling import decision_key, identity
from methane.services.executive import Executive, Mission
from methane.services.plant import PlantServices
from methane.services.registry import Registry
from methane.services.resources import Booking, Ledger, Resource
from methane.services.support import Support
from methane.services.visits import VisitPlan

VERSION = "service-planning-snapshot/3"


def typed(cls, value, **arrays):
    """Decode only explicitly registered data contracts, with constructor checks."""
    data = copy.deepcopy(value)
    for key, item_type in arrays.items():
        if key in data:
            data[key] = tuple(item_type(**v) if item_type else v for v in data[key])
    return cls(**data)


def context(value):
    return typed(Context, value, readings=Reading)


def asset(value):
    return typed(
        Asset, value, capabilities=None, tools=None, support_resources=Quantity, sources=Source
    )


def interface(value):
    return typed(
        Interface,
        value,
        actions=None,
        required_tools=None,
        requirements=Requirement,
        exclusive_resources=None,
    )


def capability(value):
    return typed(
        Capability,
        value,
        consumables=Quantity,
        requirements=Requirement,
        shared_resources=Quantity,
        sources=Source,
        acceptance=Requirement,
        hourly_consumables=Quantity,
    )


def plan(value):
    data = copy.deepcopy(value)
    data.update(
        order=typed(WorkOrder, data["order"], evidence=Reading),
        asset=asset(data["asset"]),
        interface=interface(data["interface"]),
        capability=capability(data["capability"]),
        context=context(data["context"]),
        stages=tuple(
            typed(
                Stage,
                s,
                consumables=Quantity,
                reservations=Quantity,
                requirements=Requirement,
                hourly_consumables=Quantity,
            )
            for s in data["stages"]
        ),
    )
    return MissionPlan(**data)


def catalogue(value):
    return Registry(
        [asset(a) for a in value["assets"]],
        [interface(i) for i in value["interfaces"]],
        [capability(c) for c in value["capabilities"]],
        [Resource(**r) for r in value["resources"]],
        Access([typed(Edge, e, mobility=None, requirements=Requirement) for e in value["access"]]),
    )


def capture(runtime):
    """Freeze original recipe inputs; returning data does not accept any work."""
    runtime._require_prepared()
    from methane.services.procedures import capture as procedure_choices

    recipes, procedures = {}, {}
    for order in runtime.orders:
        if order["status"] != "queued":
            continue
        try:
            # Undecorated recipes let later starts check their own shift and
            # charge crew hours once, including recomposed shared journeys.
            recipe = runtime._build(order)
            recipes[order["id"]] = dict(plan=recipe.to_dict(), unavailable=None)
            choices = procedure_choices(runtime, recipe)
            if choices:
                procedures[order["id"]] = choices
        except (ValueError, KeyError) as exc:
            recipes[order["id"]] = dict(plan=None, unavailable=str(exc))
    definitions = runtime.registry.manifest()
    snapshot = dict(
        schema_version=VERSION,
        original_decision_key=decision_key(runtime),
        service_source=dict(SOURCE_IDENTITY),
        catalogue_id=identity(definitions),
        at_hour=runtime.executive.at_hour,
        context=asdict(runtime._context),
        config=asdict(runtime.config),
        **(
            dict(autonomy=copy.deepcopy(runtime.autonomy))
            if getattr(runtime, "autonomy", None)
            else {}
        ),
        **(
            dict(uncertainty_beliefs=copy.deepcopy(runtime.belief_record))
            if getattr(runtime, "belief_record", None)
            else {}
        ),
        options=asdict(runtime.options),
        available_service_pv_kw=runtime._available_service_pv,
        standby=copy.deepcopy(runtime._standby),
        installed=copy.deepcopy(runtime.interval["assets"]),
        orders=copy.deepcopy(runtime.orders),
        observed_orders=copy.deepcopy(runtime.public()["orders"]),
        recipes=recipes,
        procedure_choices=procedures,
        resources=dict(
            stock=copy.deepcopy(runtime.ledger.stock),
            holds=copy.deepcopy(runtime.ledger.holds),
            bookings=[asdict(b) for b in runtime.ledger.bookings],
            seen_missions=sorted(runtime.ledger.seen_missions),
        ),
        missions=[
            dict(
                plan=m.plan.to_dict(), stage_index=m.stage_index, entered=m.entered, status=m.status
            )
            for m in runtime.executive.missions.values()
        ],
        visits=[v.to_dict() for v in runtime.executive.visits.values()],
        observed_visits=copy.deepcopy(runtime.executive.public().get("visits", [])),
        readiness={
            a: {
                "ready": runtime._available(a),
                "present": runtime._available(a, require_ready=False),
            }
            for a in runtime.registry.assets
        },
        hardware_operable={
            name: runtime.hardware_operable(name)
            for name in ("cleaner", "rover", "dock", "portable")
        },
        returned_orders=sorted(runtime.support.returned) if runtime.support else [],
        optical=None,
        scope="Original current observations, recipes and reservations, before accepting new work. Existing commitments retain observed cursors. No physical outcomes, private variates or future weather; continuation remains conditional.",
    )
    if runtime.optical:
        optical = runtime.optical
        snapshot["optical"] = dict(
            plant=optical.plant.to_dict(),
            weather=asdict(optical.weather),
            baseline=copy.deepcopy(optical.baseline),
            surface=getattr(optical, "planning_surface", optical.surface).snapshot(),
            observed_treatments=copy.deepcopy(
                optical.observed_treatments()
                if hasattr(optical, "observed_treatments")
                else optical.surface.events
            ),
        )
    snapshot["snapshot_id"] = identity(snapshot)
    return dict(snapshot=snapshot, catalogue=definitions)


class PlanningExecutive(Executive):
    """Retain dry-run feasibility, but provide no execution or acceptance port."""

    def _disabled(self, *args, **kwargs):
        raise ValueError("A saved planning snapshot cannot execute or accept work")

    submit = submit_visit = advance = interrupt = _disabled


class PlanningSupport:
    decorate = Support.decorate

    def __init__(self, options, returned):
        self.o, self.returned = options, frozenset(returned)

    def recovered(self, mission):
        return mission.plan.order.order_id in self.returned


class RecordedServices:
    """Current planning kernels over recorded inputs, never reconstructed truth.

    The original snapshot and the current service source are both exposed. A
    changed implementation must be labelled as current-model replanning by its
    caller; it is not the original recorded calculation. Source-run data are
    copied, and this adapter has no dispatch/execute or random-effect methods.
    """

    _require_prepared = PlantServices._require_prepared
    _peak = PlantServices._peak
    propose = PlantServices.propose
    duration_envelope = PlantServices.duration_envelope
    propose_charge = PlantServices.propose_charge
    propose_visit = PlantServices.propose_visit
    planned_demands = PlantServices.planned_demands
    isolation_horizon = PlantServices.isolation_horizon

    def __init__(self, snapshot, definitions):
        s = copy.deepcopy(snapshot)
        if s.get("schema_version") not in (
            "service-planning-snapshot/1",
            "service-planning-snapshot/2",
            VERSION,
        ):
            raise ValueError("Unsupported or missing original service planning snapshot")
        if identity({k: v for k, v in s.items() if k != "snapshot_id"}) != s.get("snapshot_id"):
            raise ValueError("Service planning snapshot integrity mismatch")
        if identity(definitions) != s["catalogue_id"]:
            raise ValueError("Service planning catalogue does not match the original snapshot")
        self.snapshot_id = s["snapshot_id"]
        self.original_decision_key = s["original_decision_key"]
        self.original_service_source = s["service_source"]
        self.source_matches = self.original_service_source == SOURCE_IDENTITY
        self.config = FieldOperations(**s["config"])
        self.autonomy = s.get("autonomy")
        self.belief_record = s.get("uncertainty_beliefs")
        self.options = ServiceSystem(**s["options"])
        self.registry = catalogue(definitions)
        self._context = context(s["context"])
        if self._context.at_hour != s["at_hour"]:
            raise ValueError("Service snapshot decision and observation clocks disagree")
        self._decision_phase = "prepared"
        self._available_service_pv = s["available_service_pv_kw"]
        self._standby = s["standby"]
        self.interval = {"assets": s["installed"]}
        self.orders = s["orders"]
        self.observed_orders = {o["id"]: o for o in s.get("observed_orders", [])}
        for order in self.observed_orders.values():
            receipt = order.get("reported")
            if receipt and not (
                0
                <= receipt.get("completed_at", float("inf"))
                <= receipt.get("available_at", float("inf"))
                <= s["at_hour"]
            ):
                raise ValueError("A planning snapshot cannot contain an unavailable work receipt")
        self.observed_visits = s.get("observed_visits")
        if self.observed_visits is not None and any(
            v.get("returned_at") is not None and not 0 <= v["returned_at"] <= s["at_hour"]
            for v in self.observed_visits
        ):
            raise ValueError("A planning snapshot cannot contain a future observed return")
        self.recipes = s["recipes"]
        self.procedure_choices = s.get("procedure_choices")
        self.chosen_procedures = {}
        self.readiness = s["readiness"]
        self._hardware_operable = s["hardware_operable"]
        self.ledger = Ledger(self.registry.resources.values())
        resources = s["resources"]
        self.ledger.stock = resources["stock"]
        self.ledger.holds = resources["holds"]
        self.ledger.bookings = [Booking(**b) for b in resources["bookings"]]
        self.ledger.seen_missions = set(resources["seen_missions"])
        self.executive = PlanningExecutive(self.ledger, None)
        self.executive.at_hour = s["at_hour"]
        self.executive.missions = {
            m["plan"]["order"]["order_id"]: Mission(**{**m, "plan": plan(m["plan"])})
            for m in s["missions"]
        }
        self.executive.visits = {
            v["visit_id"]: VisitPlan(**{**v, "members": tuple(plan(p) for p in v["members"])})
            for v in s["visits"]
        }
        self.support = (
            PlanningSupport(self.options, s["returned_orders"])
            if self.options.support_model != "none"
            else None
        )
        self.optical = None
        if s["optical"]:
            o = s["optical"]
            surface = copy.deepcopy(o["surface"])
            self.optical = SimpleNamespace(
                plant=Plant(**o["plant"]),
                weather=WeatherConfig(**o["weather"]),
                baseline=o["baseline"],
                surface=SimpleNamespace(
                    snapshot=lambda: copy.deepcopy(surface), events=o["observed_treatments"]
                ),
            )
        self._validate()

    def _validate(self):
        """Reject inconsistent records rather than creating a feasible substitute."""
        now = self.executive.at_hour
        if set(self.ledger.stock) != {
            r.resource_id for r in self.registry.resources.values() if r.kind == "stock"
        }:
            raise ValueError("Recorded service stock does not match declared resources")
        for key, amount in self.ledger.stock.items():
            if (
                not 0 <= amount <= self.ledger.specs[key].capacity
                or self.ledger.available(key) < -1e-8
            ):
                raise ValueError("Invalid recorded stock or reservation: " + key)
        for entry in self.recipes.values():
            if entry["plan"] is not None:
                p = plan(entry["plan"])
                if p.context != self._context:
                    raise ValueError("Recipe does not use the original observation context")
        for m in self.executive.missions.values():
            if m.plan.context.at_hour > now:
                raise ValueError("Accepted commitment contains future information")

    def _build(self, order):
        entry = self.recipes.get(order["id"])
        if entry is None or entry["plan"] is None:
            raise ValueError(
                entry["unavailable"] if entry else "No original recipe for this request"
            )
        return plan(entry["plan"])

    def choose_procedure(self, order_id, procedure_id):
        """Replace one recipe in this private planning copy, with no execution."""
        from methane.services.procedures import identifier, selected

        choice = selected(dict(procedure_choices=self.procedure_choices), order_id, procedure_id)
        order = next((o for o in self.orders if o["id"] == order_id), None)
        if order is None or order["status"] != "queued":
            raise ValueError("Only newly selected queued work can change procedure")
        if choice["plan"] is None:
            raise ValueError(choice["unavailable"] or "Original procedure unavailable")
        replacement = plan(choice["plan"])
        original = self._build(order)
        if (
            replacement.context != self._context
            or replacement.order.order_id != order_id
            or replacement.order.requested_at != original.order.requested_at
            or replacement.order.evidence != original.order.evidence
            or replacement.interface.target_asset_id != original.interface.target_asset_id
            or identifier(
                replacement.asset.asset_id,
                replacement.capability.capability_id,
                replacement.interface.interface_id,
            )
            != procedure_id
            or replacement.asset != self.registry.assets.get(replacement.asset.asset_id)
            or replacement.capability
            != self.registry.capabilities.get(replacement.capability.capability_id)
            or replacement.interface
            != self.registry.interfaces.get(replacement.interface.interface_id)
        ):
            raise ValueError(
                "Recorded alternative does not match its original request and catalogue"
            )
        self.recipes[order_id] = dict(plan=choice["plan"], unavailable=None)
        self.chosen_procedures[order_id] = procedure_id

    def _available(self, asset_id, require_ready=True):
        return self.readiness.get(asset_id, {}).get("ready" if require_ready else "present", False)

    def hardware_operable(self, name):
        return self._hardware_operable[name]

    def public(self):
        # Fingerprint the planning inputs, not an invented copy of historical
        # telemetry. Its original full decision key remains an explicit link.
        return copy.deepcopy(
            dict(
                snapshot_id=self.snapshot_id,
                original_decision_key=self.original_decision_key,
                resources=dict(
                    stock=self.ledger.stock,
                    holds=self.ledger.holds,
                    bookings=[asdict(b) for b in self.ledger.bookings],
                ),
                orders=[self.observed_orders.get(o["id"], o) for o in self.orders],
                **(
                    dict(executive=dict(visits=self.observed_visits))
                    if self.observed_visits is not None
                    else {}
                ),
                **(dict(procedures=self.chosen_procedures) if self.chosen_procedures else {}),
            )
        )
