"""Causal adapter between the fractional service executive and the hourly plant.

The local supervisor sees diagnosis and declared readings. Only IntervalEffects
is temporarily bound to FaultState, after dispatch. Work effects are committed
AFTER plant execution, so they cannot repair an interval already in progress.
"""

import copy
import hashlib
from dataclasses import asdict, replace
from math import isfinite

from methane.audit import check, require
from methane.faults import HARDWARE_MODEL, LEGACY_HARDWARE_MODEL
from methane.services import SOURCE_IDENTITY
from methane.services.adapters import fixed, schedule
from methane.services.contracts import Context, Quantity, Reading, WorkOrder, available_boundary
from methane.services.core import ASSETS, ISOLATION, definition
from methane.services.executive import Executive, Receipt
from methane.services.resources import Ledger

VERSION = "plant-service-contracts/1"
LIVE = ("scheduled", "active")


def overlap(start, end, a, b):
    return max(0, min(end, b) - max(start, a))


class IntervalEffects:
    """Private execution port. Fault mutations are deferred to commit()."""

    def __init__(
        self, config, options, seed, surface=None, ledger=None, *, hardware_model=HARDWARE_MODEL
    ):
        self.hardware_model = hardware_model
        self.surface, self.ledger = surface, ledger
        self.treatments, self.pass_efficacy = [], {}
        self.config, self.options, self.seed = config, options, seed
        self._faults = None
        self.pending = []
        self.charge = []
        self.cleanings = 0
        self.hour = None
        self.support = None
        self.inspection_samples = []
        self.hardware_procedures = []
        self.random_events = None
        if options.outcome_randomness != "legacy-reason/1":
            from methane.services.randomness import Events

            self.random_events = Events(seed)
        self._random_start = 0

    def draw(self, plan, channel):
        if self.random_events is not None:
            if self._faults is None:
                raise ValueError("Outcome draws are private execution, not planning information")
            return self.random_events.draw(plan, channel, self.hour)
        # Action occurrence, not controller identity or unrelated sensor draws.
        key = f"{self.seed}/{plan.order.action}/{plan.order.reason}/{channel}"
        return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64

    def bind(self, hour, faults):
        if self._faults is not None:
            raise ValueError("Execution port already bound")
        if faults.policy.hardware_model != self.hardware_model:
            raise ValueError("Execution and fault configuration select different hardware models")
        self.hour, self._faults = hour, faults
        self.pending, self.charge, self.cleanings = [], [], 0
        self.treatments = []
        self.inspection_samples = []
        self.hardware_procedures = []
        self._random_start = self.random_events.count if self.random_events is not None else 0

    def before_stage(self, plan, stage, at_hour):
        if (
            self.hardware_model == LEGACY_HARDWARE_MODEL
            and not self.options.equipment_recovery_enabled
        ):
            return None
        if self.hardware_model == HARDWARE_MODEL and plan.order.action == "self-test":
            return None  # Electronics execute a test; its response checks the physical drive.
        if self._faults is None:
            raise ValueError("Hardware interlocks require the private execution port")
        from methane.services.hardware import before_stage

        return before_stage(plan, stage, at_hour, self.hour, self._faults)

    def next_event(self, plan, at_hour):
        if self.surface is None or plan.order.action not in (
            "clean-section",
            "portable-clean-section",
        ):
            return None
        if self.draw(plan, "mission-failure") >= self.config.mission_failure_probability:
            return None
        start, end, _ = next((a, b, s) for a, b, s in schedule(plan) if s.effect)
        failed_at = start + (end - start) * self.options.work_failure_fraction
        return failed_at if failed_at > at_hour else None

    def progress(self, plan, stage, started, completed):
        if (
            self.surface is None
            or plan.order.action not in ("clean-section", "portable-clean-section")
            or stage.phase != "perform"
        ):
            return None
        if self._faults is None:
            raise ValueError("Continuous effects require the execution port")
        a, b, _ = next((a, b, s) for a, b, s in schedule(plan) if s.effect)
        portable = plan.order.action == "portable-clean-section"
        # The private execution recipe already includes persistent and job
        # clocks. A full pass covers its section once, however long it takes.
        # Reusing only the configured persistent factor would disagree with
        # scaled brush/water consumption when a fresh job multiplier differs.
        rate = (
            self.surface.section(plan.interface.target_asset_id)["area_m2"] / stage.duration_hours
        )
        area = (completed - started) * rate
        key = plan.order.order_id
        if portable:
            self.pass_efficacy[key] = self.options.portable_loose_removal
        elif key not in self.pass_efficacy:
            remaining = self.ledger.stock["brush:cleaner"] + area
            self.pass_efficacy[key] = (
                self.config.cleaning_removal_fraction * remaining / self.options.brush_life_m2
            )
        efficacy = self.pass_efficacy[key]
        treatment = dict(
            section=plan.interface.target_asset_id,
            order_id=key,
            start_m2=(started - a) * rate,
            end_m2=min(
                self.surface.section(plan.interface.target_asset_id)["area_m2"],
                (completed - a) * rate,
            ),
            efficacy_start=efficacy,
            efficacy_end=efficacy,
            started_at=started,
            completed_at=completed,
            effective_at=available_boundary(completed),
        )
        if portable:
            treatment.update(
                method="portable-" + self.options.portable_cleaner,
                adhered_removal=self.options.portable_adhered_removal
                if self.options.portable_cleaner == "wet"
                else 0,
            )
        self.treatments.append(treatment)
        failure = a + (b - a) * self.options.work_failure_fraction
        interrupted = (
            self.draw(plan, "mission-failure") < self.config.mission_failure_probability
            and abs(completed - failure) < 1e-8
        )
        return Receipt(
            "Cleaning interrupted; covered area remains treated; asset requires retrieval"
            if interrupted
            else "Partial treatment recorded; optical effect at next decision boundary",
            physical_effects=(treatment,),
            interrupted=interrupted,
        )

    def perform(self, plan, completed_at):
        if self._faults is None or not self.hour < completed_at <= self.hour + 1:
            raise ValueError("Physical effects require the current execution interval")
        c, o = self.config, self.options
        action, boundary = plan.order.action, available_boundary(completed_at)
        if o.equipment_recovery_enabled:
            from methane.services.hardware import ACTIONS, perform

            if action in ACTIONS:
                receipt = perform(
                    plan,
                    completed_at,
                    self._faults,
                    self.hour,
                    c.repair_success_probability,
                    self.draw,
                )
                for effect in receipt.physical_effects:
                    if effect["kind"] == "hardware-procedure":
                        self.hardware_procedures.append({**effect, "order_id": plan.order.order_id})
                if action in ("guided-return", "pack-return"):
                    order = next(
                        q for q in self.support.rt.orders if q["id"] == plan.order.order_id
                    )
                    event = dict(
                        kind=action,
                        order_id=order["id"],
                        robot=order["robot"],
                        origin_order=order["origin_order"],
                        location=order["recovery_location"],
                        completed_at=completed_at,
                        effective_at=boundary,
                    )
                    self.support.events.append(event)
                    receipt = replace(receipt, physical_effects=(*receipt.physical_effects, event))
                return receipt
        if self.support and action in (
            "crew-return",
            "retrieve",
            "self-test",
            "restock",
            "replace-brush",
            "routine-service",
        ):
            state = None
            if action == "self-test" and self.hardware_model == HARDWARE_MODEL:
                name = next(n for n in ("cleaner", "rover") if ASSETS[n] == plan.asset.asset_id)
                state = self._faults.service_hardware_truth(name, self.hour)
            return self.support.perform(plan, completed_at, self.draw, hardware_state=state)
        if action.startswith("charge-"):
            name = action.removeprefix("charge-")
            energy = sum(s.bus_kw * s.duration_hours for s in plan.stages)
            self.charge.append((name, energy, boundary, plan.order.order_id))
            return Receipt("Charging interval completed; energy posted at the hourly boundary")
        if (
            plan.asset.battery_resource
            and action != "clean-section"
            and self.draw(plan, "mission-failure") < c.mission_failure_probability
        ):
            return Receipt("Mission interrupted; asset requires assistance", interrupted=True)
        if action == "read-trip-contact":
            if o.inspection_model == "referenced-contact/1":
                from methane.services.inspection import sample

                reader = "fixed" if plan.asset.mobility == "fixed" else "mobile"
                observations, trace = sample(
                    self._faults.inspection_signal(self.hour, reader, completed_at),
                    reader,
                    completed_at,
                    plan.order.order_id,
                    self.seed,
                    o,
                )
                self.inspection_samples.append(trace)
                return Receipt(
                    "Prepared contact and reader references sampled; no physical repair performed",
                    observations,
                )
            unreadable = self.draw(plan, "unreadable") < o.contact_unreadable_probability
            value = self._faults.inspect_panel(self.hour)["latched"]
            if self.draw(plan, "contact-error") < o.contact_error_probability:
                value = not value
            reading = Reading(
                "trip-contact",
                None if unreadable else value,
                "boolean",
                completed_at,
                boundary,
                "bounded-contact-read/1:" + plan.order.order_id,
                "unavailable" if unreadable else "usable",
            )
            return Receipt(
                "Trip contact unreadable"
                if unreadable
                else "Trip contact read; no repair performed",
                (reading,),
            )
        if action in ("clean-section", "portable-clean-section"):
            self.cleanings += 1
            return Receipt("Section pass completed; only compatible surface material treated")
        if action == "clean-array":
            self.cleanings += 1
            return Receipt(
                "Brush pass completed; lumped soiling effect available at the next boundary"
            )
        if action in ("reset", "module-replacement", "flow-calibration"):
            success = self.draw(plan, "repair") < c.repair_success_probability
            self.pending.append((action, boundary, success, plan.order.order_id))
            # Intentionally no success observation. Plant tracking must establish recovery.
            return Receipt("Procedure completed; operating recovery remains unverified")
        raise ValueError("Unsupported physical action: " + action)

    def commit(self):
        if self._faults is None:
            raise ValueError("No pending execution interval")
        effects = []
        for action, boundary, success, order in self.pending:
            effect = self._faults.service(action, boundary - 1, success)
            if self.random_events is not None:
                effect["procedure_passed"] = success
            effects.append({**effect, "order_id": order})
        for procedure in self.hardware_procedures:
            effect = self._faults.service_hardware(
                procedure["target"],
                procedure["action"],
                procedure["effective_at"] - 1,
                procedure["successful"],
            )
            effects.append(
                {
                    **effect,
                    "effective_at": procedure["effective_at"],
                    "order_id": procedure["order_id"],
                    "kind": "hardware-procedure",
                }
            )
        self._faults = None
        return effects


class PlantServices:
    def __init__(
        self,
        config,
        options,
        seed,
        nameplate_kw,
        optical=None,
        *,
        hardware_model=HARDWARE_MODEL,
        record_planning=False,
        execution_config=None,
        execution_options=None,
        autonomy=None,
        support_observations=None,
    ):
        if hardware_model not in (HARDWARE_MODEL, LEGACY_HARDWARE_MODEL):
            raise ValueError("Unknown service-hardware execution model")
        self.hardware_model = hardware_model
        if type(record_planning) is not bool:
            raise ValueError("Planning recording must be an explicit boolean")
        self.record_planning = record_planning
        self.autonomy = copy.deepcopy(autonomy)
        if not self.autonomy:
            from methane.services.uncertain_timing import GROUPS

            if any(
                getattr(execution_options or options, key + "_time_factor") != 1 for key in GROUPS
            ):
                raise ValueError(
                    "Non-unit service time factors require a declared duration envelope"
                )
        self._support_observations = support_observations
        self.beliefs = None
        self.belief_record = None
        self.surface_observation = None
        self._reference_monitors = None
        if self.autonomy:
            from methane.autonomy import Beliefs, ReferenceMonitors

            self.beliefs = Beliefs(self.autonomy, 1 - config.mission_failure_probability)
            self._reference_monitors = ReferenceMonitors(self.autonomy, seed)
        self.planning_catalogues = {}
        self.optical = optical
        if (options.cleaning_model == "section-optical/1") != (optical is not None):
            raise ValueError(
                "Optical service configuration requires the section conversion adapter"
            )
        self.environment = {}
        self.config, self.options, self.nameplate_kw = config, options, nameplate_kw
        self.registry = definition(
            config, options, optical.surface if optical else None, hardware_model=hardware_model
        )
        self.ledger = Ledger(self.registry.resources.values())
        self._effects = IntervalEffects(
            execution_config or config,
            execution_options or options,
            seed,
            optical.surface if optical else None,
            self.ledger,
            hardware_model=hardware_model,
        )
        self.executive = Executive(self.ledger, self._effects)
        if self.autonomy:
            from methane.services.uncertain_timing import GROUPS, BoundedExecutive

            actual_options = execution_options or options
            factors = {key: getattr(actual_options, key + "_time_factor") for key in GROUPS}
            job_clock = None
            if "duration_model" in self.autonomy:
                from methane.services.job_clock import JobClock

                job_clock = JobClock(self.autonomy["duration_model"], factors, seed)
            self.executive = BoundedExecutive(
                self.ledger,
                self._effects,
                factors,
                job_clock=job_clock,
            )
        from methane.services.hardware import HardwareMonitor

        self.hardware = HardwareMonitor(self) if hardware_model == HARDWARE_MODEL else None
        self.soiling = optical.surface.loose_mean() if optical else config.initial_soiling_fraction
        self.orders, self.messages = [], []
        self.interval, self._context, self._executed = None, None, False
        self._decision_phase = "idle"
        self._available_service_pv = None
        self._standby = None
        self._snapshots = {}
        self._inspection_status = None
        self.support = None
        self.cleaning_policy = None
        if options.cleaning_policy != "legacy-condition":
            from methane.services.local_policy import CleaningPolicy

            self.cleaning_policy = CleaningPolicy(self)
        if options.support_model != "none":
            from methane.services.support import Support

            self.support = Support(self)
            self._effects.support = self.support

    @property
    def version(self):
        return (
            "plant-service-contracts/12"
            if self.options.crew_return_enabled
            else "plant-service-contracts/11"
            if self.hardware is not None
            else "plant-service-contracts/10"
            if self._effects.random_events is not None
            else "plant-service-contracts/9"
            if self.cleaning_policy or self.options.inspection_interface != "legacy-prepared"
            else "plant-service-contracts/8"
            if self.options.maintenance_enabled or self.options.dock_standby_kw
            else "plant-service-contracts/7"
            if self.options.equipment_recovery_enabled
            else "plant-service-contracts/6"
            if self.options.visit_bundling_enabled
            else "plant-service-contracts/5"
            if self.options.inspection_model == "referenced-contact/1"
            else "plant-service-contracts/4"
            if self.options.portable_cleaner != "none"
            else "plant-service-contracts/3"
            if self.support
            else "plant-service-contracts/2"
            if self.optical
            else VERSION
        )

    def manifest(self):
        return dict(
            implementation_id=self.version,
            source=dict(SOURCE_IDENTITY),
            asset_ids={k: v for k, v in ASSETS.items() if v in self.registry.assets},
            parameters=asdict(self.config),
            service_parameters=asdict(self.options),
            **({"hardware_model": self.hardware_model} if self.hardware else {}),
            **(
                {
                    "outcome_randomness": {
                        "implementation_id": self.options.outcome_randomness,
                        "key": "Seed, target asset, action, accepted request ordinal and outcome channel",
                        "scope": "Bernoulli mission and procedure outcomes. Referenced-reader noise retains its separate reader/time/channel model. Uniform draws are retrospective truth, withheld from the controller.",
                        "cancellation": "Accepted requests retain their ordinal if later cancelled. Unaccepted candidates do not consume an ordinal.",
                        "matching": "Changes in request wording, order identifiers, actor, scheduled hour or unrelated targets/actions do not change a matched variate. Different requests or channels are separate draws; equal seeds do not force equal physical outcomes under changed probabilities or conditions.",
                    }
                }
                if self._effects.random_events is not None
                else {}
            ),
            definitions=self.registry.manifest(),
            information_boundary="Dispatch uses recorded diagnosis, current support availability and eligible bounded contact readings. Execution truth stays in the private effect port.",
            timing="Fractional work phases; integrated hourly electricity; repair and soiling changes at the next decision boundary. Work/verification isolation conservatively covers intersecting plant intervals.",
            power_policy=(
                "Dock controls receive a full-rate priority grant from current PV and available plant-battery energy. Remaining measured solar bounds active service/charging rates. Future service loads are not yet jointly optimized with production."
                if self.options.dock_standby_kw
                else "Local solar-only service rule. Current measured solar power bounds concurrent fixed service/charging rates. Future service loads are not yet jointly optimized with production."
            ),
            solar_scope="Piecewise section coverage; loose material, adhered fouling and permanent damage are separate. Dry brushing removes only loose material; compatible portable wet treatment also reduces its configured adhered fraction. Damage is unchanged. Area-mean optical transmission enters the section model before temperature conversion and clipping."
            if self.optical
            else "Legacy lumped additional available-DC soiling proxy, after conversion; not yet section optical cleaning.",
            surface_model={
                "implementation_id": self.optical.surface.version,
                "initial": self.optical.surface.initial_state,
            }
            if self.optical
            else None,
            limitations=[
                "Actuator failures apply independently of recovery permission; no feedback means unobserved, not proven healthy. Retrieval changes location only; tests observe the actual drive."
                if self.hardware
                else "Legacy compatibility: service-hardware faults apply only with equipment recovery enabled. This model must not rank recovery policies under hardware faults.",
                "Declared routes and ideal interlocks; no collision, emergency or hazard-certification model",
                "Referenced readers expose signal, zero/span checks, delay, channel isolation and shared-contact limitations; no visual fault oracle"
                if self.options.inspection_model == "referenced-contact/1"
                else "Contact reader has seeded errors/unreadable outcomes; no visual fault oracle",
                "Bounded remote release and a separate test may permit guided return; unsuccessful assistance requires retrieval, compatible module replacement and post-work tracking. Portable operators can pack and return their stopped tool."
                if self.options.equipment_recovery_enabled
                else "Failed mobile tasks require retrieval; the optional logistics model returns them to dock and requires an observed supervised drive test",
                "Combined visits use the same crew, declared transfer routes and atomic current-stock reservations; every job keeps its own acceptance test"
                if self.options.visit_bundling_enabled
                else "Crew interventions use separate journeys",
                "Reset clears only a latched trip; replacement changes only capacity; calibration changes only the flow channel",
                "Model needs informative operating probes to confirm recovery; work completion alone never restores the observer estimate",
                "Fixed reader and reset controller have illustrative owned capital; contracted crew travel is priced through callout, with site work priced hourly",
            ],
        )

    @property
    def energy(self):
        return {name: self.ledger.stock.get("energy:" + name, 0) for name in ("cleaner", "rover")}

    def context(self, hour, diagnosis):
        c, o = self.config, self.options
        readings = [
            Reading(channel, value, "boolean", hour, hour, "declared-support-fixture/1")
            for channel, value in (
                ("route-open", c.route_open),
                ("dock-available", c.dock_available),
                ("communications", o.communications_available),
                (
                    "crew-available",
                    o.crew_available and (self.support is None or self.support.on_shift(hour)),
                ),
                ("calibration-reference", o.calibration_reference_available),
            )
        ]
        if self._support_observations is not None:
            readings = self._support_observations.at(hour, readings)
        if self._standby is not None:
            readings.append(
                Reading(
                    "dock-control-powered",
                    self._standby["control_available"],
                    "boolean",
                    hour,
                    hour,
                    "dock-standby/1",
                )
            )
        if o.inspection_interface != "legacy-prepared":
            from methane.services.local_policy import port_reading

            readings.append(port_reading(o, hour))
        if self.optical:
            ambient = self.environment.get("ambient_c")
            if (
                isinstance(ambient, bool)
                or not isinstance(ambient, (float, int))
                or not isfinite(ambient)
            ):
                ambient = None
            readings.append(
                Reading(
                    "ambient-c",
                    ambient,
                    "°C",
                    hour,
                    hour,
                    "current-ambient-sensor/1",
                    "usable" if ambient is not None else "unavailable",
                )
            )
            readings.append(
                Reading(
                    "row-accessible",
                    o.row_accessible,
                    "boolean",
                    hour,
                    hour,
                    "declared-row-interface/1",
                )
            )
            for channel, key, unit, assumed in (
                ("wind-mps", "wind_mps", "m/s", o.assumed_wind_mps),
                ("rain-mmph", "rain_mmph", "mm/h", o.assumed_rain_mmph),
            ):
                value = assumed if o.environment_source == "assumed" else self.environment.get(key)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not isfinite(value)
                    or value < 0
                ):
                    value = None
                readings.append(
                    Reading(
                        channel,
                        value,
                        unit,
                        hour,
                        hour,
                        "assumed-service-weather/1"
                        if o.environment_source == "assumed"
                        else "recorded-service-weather/1",
                        "usable" if value is not None else "unavailable",
                    )
                )
        # Timestamp the START of the measured interval. An observation ending at
        # repair time is not evidence of operation AFTER that repair.
        readings += [
            Reading(
                channel,
                value,
                "boolean",
                max(0, hour - 1),
                hour,
                "process-diagnosis/1",
                "usable" if diagnosis.informative else "uncertain",
            )
            for channel, value in (
                (
                    "capacity-restored",
                    diagnosis.capacity_kw >= self.nameplate_kw * 0.999
                    and diagnosis.tracking_residual <= 0.1,
                ),
                (
                    "flow-restored",
                    not diagnosis.flow_isolated and abs(diagnosis.flow_residual) <= 0.1,
                ),
            )
        ]
        context = Context(
            hour,
            (
                *readings,
                *(self.support.readings(hour) if self.support else ()),
                *(
                    self.support.equipment.readings()
                    if self.support and self.support.equipment
                    else ()
                ),
                *self.executive.observations(hour),
            ),
        )
        if o.inspection_model == "referenced-contact/1":
            from methane.services.inspection import evidence, reading

            context = Context(hour, (*context.readings, *self.contact_changes(hour)))
            report = evidence(
                context,
                o,
                self.orders,
                commissioned_only=getattr(self, "_capacity_request_policy", "local")
                == "investigation",
            )
            context = Context(hour, (*context.readings, reading(report)))
        return context

    def _queue(self, kind, hour, incident, reason, section=None, **metadata):
        if kind not in ("cleaning", "portable-cleaning") and any(
            o["kind"] == kind and o["incident"] == incident for o in self.orders
        ):
            return
        sequence = 1 + sum(o["kind"] == kind for o in self.orders)
        order = dict(
            id=f"SVC-{len(self.orders) + 1:04}",
            kind=kind,
            incident=incident,
            created_hour=hour,
            reason=reason,
            sequence=sequence,
            section=section,
            **metadata,
            status="queued",
            phase="queued",
            evidence=[asdict(r) for r in self._context.readings],
        )
        self.orders.append(order)
        self.messages.append(
            dict(hour=hour, component="services", label=f"{kind}: queued ({order['id']})")
        )
        return order

    def _policy(self, hour, diagnosis, *, capacity_requests=True):
        c, o = self.config, self.options
        if capacity_requests and o.inspection_model == "referenced-contact/1":
            from methane.services.inspection import policy

            policy(self, hour, diagnosis)
        if diagnosis.active_incident:
            incident = diagnosis.incidents
            if diagnosis.flow_isolated:
                self._queue(
                    "flow-calibration",
                    hour,
                    incident,
                    "Independent balance has isolated the flow channel",
                )
            if (
                diagnosis.capacity_kw < self.nameplate_kw * 0.95
                and o.inspection_model != "referenced-contact/1"
                and capacity_requests
            ):
                inspection = next(
                    (
                        q
                        for q in self.orders
                        if q["kind"] == "inspection" and q["incident"] == incident
                    ),
                    None,
                )
                if inspection is None:
                    if (
                        o.inspector != "none"
                        and (o.inspector == "fixed" or c.rover_enabled)
                        and o.inspection_interface != "enclosed-contact"
                    ):
                        self._queue(
                            "inspection", hour, incident, "Observed electrical tracking shortfall"
                        )
                    else:
                        self._queue(
                            "module-replacement",
                            hour,
                            incident,
                            "Capacity estimate is derated; known contact interface is incompatible"
                            if o.inspection_interface == "enclosed-contact"
                            else "Capacity estimate is derated; no independent contact reader configured",
                        )
                else:
                    mission = self.executive.missions.get(inspection["id"])
                    reading = self._context.latest("trip-contact")
                    applicable = (
                        reading
                        and reading.source_id.endswith(inspection["id"])
                        and hour - reading.measured_at <= o.contact_max_age_hours
                    )
                    if (
                        applicable
                        and reading.quality == "usable"
                        and reading.value
                        and c.reset_enabled
                    ):
                        self._queue(
                            "reset",
                            hour,
                            incident,
                            "A current inspection reported a latched trip contact",
                        )
                    elif applicable or (mission and mission.status in ("blocked", "stranded")):
                        self._queue(
                            "module-replacement",
                            hour,
                            incident,
                            "Derated tracking remains; reset evidence unavailable or not latched",
                        )
                reset = next(
                    (
                        self.executive.missions[q["id"]]
                        for q in self.orders
                        if q["kind"] == "reset"
                        and q["incident"] == incident
                        and q["id"] in self.executive.missions
                    ),
                    None,
                )
                if (
                    reset
                    and reset.work_completed_at is not None
                    and hour > available_boundary(reset.work_completed_at)
                    and diagnosis.informative
                    and diagnosis.tracking_residual > 0.1
                ):
                    self._queue(
                        "module-replacement",
                        hour,
                        incident,
                        "Post-reset informative tracking still falls short",
                    )
        if self.cleaning_policy:
            self.cleaning_policy.policy(hour)
            return
        busy_cleaner = any(
            q["kind"] == "cleaning"
            and (
                q["status"] == "queued"
                or (
                    q["id"] in self.executive.missions
                    and (
                        self.executive.missions[q["id"]].status in LIVE
                        or (
                            self.executive.missions[q["id"]].status == "stranded"
                            and not (
                                self.support
                                and self.support.recovered(self.executive.missions[q["id"]])
                            )
                        )
                    )
                )
            )
            for q in self.orders
        )
        if (
            c.cleaner_enabled
            and (
                any(
                    s["removable_fraction"] >= c.cleaning_threshold
                    for s in getattr(
                        self.optical, "planning_surface", self.optical.surface
                    ).public()["sections"]
                )
                if self.optical
                else self.soiling >= c.cleaning_threshold
            )
            and not busy_cleaner
            and self.ledger.available("stock:cleaning") >= 1
        ):
            if self.optical:
                target = max(
                    getattr(self.optical, "planning_surface", self.optical.surface).public()[
                        "sections"
                    ],
                    key=lambda s: (s["removable_fraction"], s["id"]),
                )
                self._queue(
                    "cleaning",
                    hour,
                    0,
                    "Observed section monitor exceeds cleaning threshold",
                    target["id"],
                )
            else:
                self._queue(
                    "cleaning", hour, 0, "Ideal lumped-loss monitor exceeds cleaning threshold"
                )

    def _target(self, kind):
        return {
            "cleaning": ("cleaner", "ARRAY/brush"),
            "inspection": (
                "fixed_reader" if self.options.inspector in ("fixed", "both") else "rover",
                "ELY/contact",
            ),
            "inspection-confirm": ("rover", "ELY/contact"),
            "reset": ("reset", "ELY/reset"),
            "module-replacement": ("crew", "ELY/module"),
            "flow-calibration": ("crew", "ELY/flow"),
            "portable-cleaning": ("portable", "PORTABLE"),
        }[kind]

    def _peak(self, hour, extra=None):
        intervals = []
        for mission in self.executive.missions.values():
            if mission.status in LIVE:
                intervals += [
                    (a, b, s.bus_kw)
                    for a, b, s in schedule(mission.plan)
                    if overlap(a, b, hour, hour + 1)
                ]
        if extra:
            intervals += [
                (a, b, s.bus_kw)
                for plan in (extra if isinstance(extra, tuple) else (extra,))
                for a, b, s in schedule(plan)
                if overlap(a, b, hour, hour + 1)
            ]
        points = {hour, *(max(hour, a) for a, _, _ in intervals)}
        return max((sum(p for a, b, p in intervals if a <= t < b) for t in points), default=0)

    def _bus(self, hour):
        return sum(
            overlap(a, b, hour, hour + 1) * stage.bus_kw
            for mission in self.executive.missions.values()
            if mission.status in LIVE
            for a, b, stage in schedule(mission.plan)
        )

    def hardware_operable(self, name):
        return (self.hardware is None or self.hardware.operable(name)) and (
            not self.support or not self.support.equipment or self.support.equipment.operable(name)
        )

    def _available(self, asset, require_ready=True):
        required = {asset}
        if asset in self.registry.assets:
            required.update(
                q.resource.removeprefix("asset:")
                for q in self.registry.assets[asset].support_resources
                if q.resource.startswith("asset:")
            )
        ready = True
        if self.hardware and require_ready:
            ready = all(
                self.hardware.operable(n)
                for n in ("cleaner", "rover", "dock", "portable")
                if ASSETS[n] in required
            )
        if self.support and require_ready:
            names = (
                ("cleaner", "rover", "dock", "portable")
                if self.options.equipment_recovery_enabled
                else ("cleaner", "rover")
            )
            name = next((n for n in names if ASSETS[n] == asset), None)
            ready = ready and (name is None or self.support.ready(name))
        return (
            ready
            and asset in self.registry.assets
            and not any(
                (
                    m.plan.asset.asset_id in required
                    or any(
                        q.resource.removeprefix("asset:") in required
                        for q in m.plan.asset.support_resources
                        if q.resource.startswith("asset:")
                    )
                )
                and (
                    m.status in LIVE
                    or (m.status == "stranded" and not (self.support and self.support.recovered(m)))
                )
                for m in self.executive.missions.values()
            )
        )

    def _build(self, order):
        if self.support and self.support.equipment:
            from methane.services.hardware import ACTIONS

            if order["kind"] in ACTIONS:
                return self.support.equipment.build(order)
        if self.support and order["kind"] in (
            "crew-return",
            "retrieve",
            "self-test",
            "restock",
            "replace-brush",
            "routine-service",
        ):
            return self.support.build(order, decorate=False)
        key, interface = self._target(order["kind"])
        if order.get("section"):
            interface = ("PORTABLE/" if key == "portable" else "ARRAY/") + order["section"]
        asset_id = ASSETS[key]
        if not self._available(asset_id):
            raise ValueError("Asset disabled, occupied or awaiting retrieval")
        cap = self.registry.capabilities[
            order["kind"] + ("/" + order["section"] if order.get("section") else "")
        ]
        # Preserve archived reason text; new matching uses accepted target/action ordinals.
        work = WorkOrder(
            order["id"],
            cap.action,
            interface,
            order["created_hour"],
            f"{order['reason']} / incident {order['incident']} / occurrence {order['sequence']}",
            evidence=tuple(Reading(**r) for r in order["evidence"]),
        )
        plan = self.registry.build(work, asset_id, cap.capability_id, self._context)
        if key == "portable":
            from methane.services.portable import prepare

            plan = prepare(plan, self.options)
        return plan

    def _accepted(self, order, plan, hour):
        random_event = None
        if self._effects.random_events is not None:
            random_event = self._effects.random_events.register(
                plan.order.order_id, plan.interface.target_asset_id, plan.order.action
            ).to_dict()
            order["stochastic_event"] = random_event
        order.update(
            status="active",
            phase="scheduled",
            started_hour=plan.starting_at,
            asset_id=plan.asset.asset_id,
        )
        order.pop("blocked", None)
        self.interval["new_missions"].append(
            {**plan.to_dict(), **({"stochastic_event": random_event} if random_event else {})}
        )

    def _dispatch(self, order, hour, available_pv):
        try:
            plan = self._build(order)
            if self.support:
                plan = self.support.decorate(plan)
            plan = self.duration_envelope(plan)
            if self._peak(hour, plan) > available_pv + 1e-9:
                raise ValueError("Current solar power cannot supply the requested service rate")
            self.executive.submit(plan)
        except (ValueError, KeyError) as exc:
            order["blocked"] = str(exc)
            return
        self._accepted(order, plan, hour)

    def _charge(self, hour, available_pv):
        c = self.config
        if self._standby is not None and not self._standby["control_available"]:
            return
        if ASSETS["dock"] not in self.registry.assets or not c.dock_available or c.dock_kw <= 0:
            return
        if not self.hardware_operable("dock"):
            return
        for name in ("cleaner", "rover"):
            asset = ASSETS[name]
            if not self._available(asset, require_ready=False):
                continue
            energy = self.ledger.stock["energy:" + name]
            deficit = getattr(c, name + "_battery_kwh") - energy
            power = min(
                c.dock_kw, max(0, available_pv - self._peak(hour)), deficit / c.charging_efficiency
            )
            if power <= 1e-9:
                continue
            kind = "charge-" + name
            cap = replace(self.registry.capabilities[kind], work_kw=power)
            work = WorkOrder(
                f"CHARGE-{hour}-{name}",
                kind,
                "DOCK/" + name,
                hour,
                "Replenish actual battery deficit with current surplus service power",
            )
            plan = fixed(
                work,
                self.registry.assets[ASSETS["dock"]],
                self.registry.interfaces[work.interface_id],
                cap,
                self._context,
            )
            try:
                self.executive.submit(plan)
            except ValueError:
                continue
            self.interval["new_missions"].append(plan.to_dict())
            break  # One shared charger; fixed cleaner-before-rover baseline.

    def prepare(
        self,
        hour,
        diagnosis,
        available_pv,
        environment=None,
        *,
        available_battery_kw=0,
        capacity_requests=True,
    ):
        """Open a decision from current evidence, before accepting new missions.

        This performs observed interruptions, verification and local work-request
        generation. Candidate construction afterwards is read-only. Existing
        missions remain commitments; no outcomes are sampled at this boundary.
        """
        if type(capacity_requests) is not bool:
            raise ValueError("Capacity request generation must be an explicit Boolean choice")
        if self._decision_phase != "idle":
            raise ValueError(
                "Finish and execute the open service decision before preparing another"
            )
        if self.executive.at_hour != hour:
            raise ValueError("Service decision must follow the previous completed interval")
        self._capacity_request_policy = "local" if capacity_requests else "investigation"
        self._decision_phase = "preparing"
        self.environment = copy.deepcopy(environment or {})
        if self.options.dock_standby_kw:
            from methane.services.standby import allocate

            self._standby = allocate(
                self.options.dock_standby_kw,
                available_pv,
                available_battery_kw,
                ASSETS["dock"] in self.registry.assets,
            )
            available_pv = max(0, available_pv - self._standby["applied_kwh"])
        self._context = self.context(hour, diagnosis)
        if self.options.inspection_model == "referenced-contact/1":
            observed = self.inspection_evidence()
            signature = (
                observed["quality"],
                observed["value"],
                tuple((c["reader"], c["quality"]) for c in observed["channels"]),
            )
            if self._inspection_status is not None and signature != self._inspection_status:
                self.messages.append(
                    dict(
                        hour=hour,
                        component="services",
                        label="Inspection evidence: " + observed["reason"],
                    )
                )
            self._inspection_status = signature
        self.executive.reconcile_verification(self._context)
        if self.beliefs:
            self.belief_record = self.beliefs.update(
                hour, self.executive.observed_durations(), self.public()["orders"]
            )
        self.interval = dict(
            version=self.version,
            hour=hour,
            assets={k: v in self.registry.assets for k, v in ASSETS.items() if k != "crew"},
            energy_before_kwh=self.energy,
            soiling_before=self.soiling,
            charge_input_kwh=0.0,
            charging_loss_kwh=0.0,
            robot_use_kwh=0.0,
            service_kits_used=0,
            calibration_kits_used=0,
            cleaning_kits_used=0,
            cleaner_hours=0.0,
            rover_hours=0.0,
            human_hours=0.0,
            human_visits=0,
            cleanings_completed=0,
            reset_attempts=0,
            repair_attempts=0,
            portable_hours=0.0,
            new_missions=[],
            retrospective_effects=[],
        )
        if self.optical:
            self.interval["surface_before"] = self.optical.surface.snapshot()
            if self.autonomy:
                observed, monitor = self._reference_monitors.surface(
                    hour, self.interval["surface_before"]
                )
                self.interval["observed_surface_before"] = observed
                self.interval["surface_monitor_before"] = monitor
            self.interval["brush_before_m2"] = self.ledger.stock["brush:cleaner"]
        if self._standby is not None:
            self.interval["standby"] = copy.deepcopy(self._standby)
        if self.options.visit_bundling_enabled:
            self.interval["new_visits"] = []
        self._snapshots = {k: len(m.events) for k, m in self.executive.missions.items()}
        self._receipt_start = self.executive.receipt_count
        self._ledger_start = len(self.ledger.events)
        if self.support:
            self.support.begin(hour)
        # Loss of electrical supply interrupts a fixed task before plant dispatch.
        for key, mission in reversed(tuple(self.executive.missions.items())):
            if self._peak(hour) <= available_pv + 1e-9:
                break
            if mission.status in LIVE and any(
                s.bus_kw and overlap(a, b, hour, hour + 1) for a, b, s in schedule(mission.plan)
            ):
                self.executive.interrupt(
                    key, "Current solar supply cannot sustain the fixed service rate"
                )
        self._policy(hour, diagnosis, capacity_requests=capacity_requests)
        if not capacity_requests:
            self.interval["capacity_request_policy"] = "observation-contingent-investigation/1"
        if self.options.portable_cleaner != "none" and self.cleaning_policy is None:
            from methane.services.portable import policy

            policy(self, hour)
        if self.support:
            self.support.policy(hour)
        self._available_service_pv = available_pv
        self._executed = False
        self._decision_phase = "prepared"
        return self.public()

    def _require_prepared(self):
        if self._decision_phase != "prepared":
            raise ValueError("Mission selection requires an open prepared service decision")

    def retry_failed(self, order_id, reason):
        """Create a distinct repair attempt after observed execution interruption.

        Completed but unverified procedures are not declared failed here. The
        caller retains its original obligation/deadline and attempt budget.
        The new request preserves the failed one and pays a new response lead.
        """
        self._require_prepared()
        old = next((q for q in self.orders if q["id"] == order_id), None)
        mission = self.executive.missions.get(order_id)
        if old is None or old["kind"] not in (
            "module-replacement",
            "flow-calibration",
            "hardware-replacement",
        ):
            raise ValueError("Only a registered repair request can be retried")
        if mission is None or mission.status not in ("blocked", "stranded", "invalid"):
            raise ValueError("A retry requires an observed interrupted or failed mission")
        if any(q.get("retry_of") == order_id for q in self.orders):
            raise ValueError("This interrupted attempt already has a successor")
        return self._repeat_order(old, reason, retry_of=order_id)

    def followup_unverified(self, order_id, assessment):
        """Rebuild a compatible substitution after a controller's measured tests.

        This port checks the current mission and evidence boundary. The bounded
        controller owns interpretation and the attempt budget; the executive
        never turns the previous unverified receipt into a successful repair.
        """
        from methane.services.coupling import identity
        from methane.services.verification import TRACKER_VERSION

        self._require_prepared()
        if (
            assessment.get("implementation_id") != TRACKER_VERSION
            or assessment.get("at_hour") != self.executive.at_hour
            or identity({k: v for k, v in assessment.items() if k != "assessment_id"})
            != assessment.get("assessment_id")
        ):
            raise ValueError("Follow-up requires an intact current observation assessment")
        old = next((q for q in self.orders if q["id"] == order_id), None)
        mission = self.executive.missions.get(order_id)
        if (
            old is None
            or old["kind"] != "module-replacement"
            or mission is None
            or mission.status != "awaiting verification"
        ):
            raise ValueError("Follow-up requires a completed unverified module substitution")
        evidence = next((a for a in assessment["attempts"] if a["order_id"] == order_id), None)
        if (
            evidence is None
            or evidence["status"] != "follow-up supported"
            or evidence["completed_at"] != available_boundary(mission.completed_at)
            or len(evidence["qualifying"]) < assessment["required_tests"]
            or any(
                q["hour"] < evidence["completed_at"] or q["available_at"] > self.executive.at_hour
                for q in evidence["qualifying"]
            )
        ):
            raise ValueError("Follow-up requires repeated eligible post-service load-test evidence")
        if any(
            q.get("retry_of") == order_id or q.get("followup_of") == order_id for q in self.orders
        ):
            raise ValueError("This unverified attempt already has a successor")
        return self._repeat_order(
            old,
            "Repeated resource-feasible post-service load tests still fall short; another qualified substitution is a bounded investigative attempt, not a confirmed diagnosis",
            followup_of=order_id,
            verification_evidence=dict(
                assessment_id=assessment["assessment_id"], attempt=copy.deepcopy(evidence)
            ),
        )

    def _repeat_order(self, old, reason, **links):
        metadata = {
            k: copy.deepcopy(v)
            for k, v in old.items()
            if k
            not in (
                "id",
                "created_hour",
                "sequence",
                "status",
                "phase",
                "evidence",
                "blocked",
                "visit_id",
                "visit_index",
                "visit_blocked",
                "retry_of",
                "followup_of",
                "verification_evidence",
                "reason",
            )
        }
        metadata.update(
            id=f"SVC-{len(self.orders) + 1:04}",
            created_hour=self.executive.at_hour,
            sequence=1 + sum(q["kind"] == old["kind"] for q in self.orders),
            status="queued",
            phase="queued",
            reason=reason,
            obligation_origin=old.get("obligation_origin", old["id"]),
            evidence=[asdict(r) for r in self._context.readings],
            **links,
        )
        self.orders.append(metadata)
        self.messages.append(
            dict(
                hour=self.executive.at_hour,
                component="services",
                label=f"Repair retry queued: {metadata['id']} after {old['id']}",
            )
        )
        return copy.deepcopy(metadata)

    def propose(self, order_id, *, starting_at=None):
        """Build a known recipe and assess it without reserving or drawing outcomes.

        Future starts retain current observations. Present readiness, route and
        stock requirements are conservative; this does not assume that another
        mission will restore hardware or replenish supplies before departure.
        """
        from methane.services.planning import assess_candidate

        self._require_prepared()
        order = next((q for q in self.orders if q["id"] == order_id), None)
        if order is None or order["status"] != "queued":
            raise ValueError("Proposal requires a queued work order")
        plan = self._build(order)
        if starting_at is not None:
            plan = replace(plan, starting_at=starting_at)
        if self.support:
            plan = self.support.decorate(plan)
        plan = self.duration_envelope(plan)
        assessment = assess_candidate(plan, self.ledger, self.executive.at_hour)
        peak = self._peak(self.executive.at_hour, plan)
        assessment["current_service_peak_kw"] = peak
        assessment["current_service_solar_kw"] = self._available_service_pv
        if peak > self._available_service_pv + 1e-9:
            assessment["feasible"] = False
            assessment["reasons"].append(
                "Current solar power cannot supply the requested service rate"
            )
        return plan, assessment

    def duration_envelope(self, plan):
        if not self.autonomy:
            return plan
        from methane.services.uncertain_timing import envelope

        value = envelope(plan, self.autonomy["duration_bounds"])
        if self.support:
            from methane.services.support import fits_shift

            if plan.asset.autonomy == "human" and not fits_shift(
                value.starting_at, value.ending_at, self.options
            ):
                raise ValueError("Duration envelope including return exceeds the crew shift")
        return value

    def propose_charge(self, name, power_kw):
        """Build an explicit current-hour charge without booking or crediting it.

        The recipe is rebuilt from the installed dock and actual battery stock;
        requested power is never silently reduced to fit a different proposal.
        Low robot energy does not prevent docking, but an absent/stranded asset,
        occupied hardware, unavailable controller or electrical limit can.
        """
        from methane.services.contracts import nonnegative
        from methane.services.planning import assess_candidate

        self._require_prepared()
        nonnegative(power_kw, "requested charging power")
        if power_kw <= 0:
            raise ValueError("An explicit charge requires positive power")
        if name not in ("cleaner", "rover") or "charge-" + name not in self.registry.capabilities:
            raise ValueError("Charging requires an installed compatible robot")
        c, hour = self.config, self.executive.at_hour
        if not c.dock_available or (
            self._standby is not None and not self._standby["control_available"]
        ):
            raise ValueError("Dock or its powered controller is unavailable")
        if not self.hardware_operable("dock"):
            raise ValueError("Observed dock hardware is unavailable")
        if any(
            m.plan.asset.asset_id == ASSETS[name]
            and m.status == "stranded"
            and not (self.support and self.support.recovered(m))
            for m in self.executive.missions.values()
        ):
            raise ValueError("Robot is stranded and has not been retrieved")
        # Whole-mission reservations below reject a robot currently away from
        # the dock. A later departure does not prevent charging before it.
        limit = min(
            c.dock_kw,
            max(0, self._available_service_pv - self._peak(hour)),
            (getattr(c, name + "_battery_kwh") - self.ledger.stock["energy:" + name])
            / c.charging_efficiency,
        )
        if power_kw > limit + 1e-9:
            raise ValueError(f"Requested charge {power_kw:g} kW exceeds current limit {limit:g} kW")
        kind = "charge-" + name
        work = WorkOrder(
            f"CHARGE-{hour}-{name}",
            kind,
            "DOCK/" + name,
            hour,
            "Explicit scheduled dock charge; credit follows actual completion",
        )
        plan = fixed(
            work,
            self.registry.assets[ASSETS["dock"]],
            self.registry.interfaces[work.interface_id],
            replace(self.registry.capabilities[kind], work_kw=power_kw),
            self._context,
        )
        return plan, assess_candidate(plan, self.ledger, hour)

    def propose_visit(self, order_ids, *, starting_at=None, index=0):
        from methane.services.visit_planning import propose

        return propose(
            self,
            order_ids,
            self.executive.at_hour if starting_at is None else starting_at,
            index=index,
        )

    def dispatch_selected(
        self,
        selections,
        *,
        charge=True,
        projection_hours=None,
        charge_requests=None,
        visit_groups=(),
    ):
        """Accept order/start recipes after rechecking actual resources in sequence.

        A caller cannot submit a modified low-energy or incompatible mission.
        Rejected candidates remain queued, with a recorded reason. Partial
        acceptance is explicit; accepted reservations are never silently undone.
        """
        self._require_prepared()
        if charge_requests is not None and charge:
            raise ValueError("Explicit charging and the local charging rule are mutually exclusive")
        charge_choices = tuple(charge_requests or ())
        if len(charge_choices) > 1:
            raise ValueError("The shared dock can accept one robot per hourly decision")
        if projection_hours is not None:
            self.planned_demands(projection_hours)  # Validate before accepting any work.
        from methane.services.visit_planning import accept as accept_visit
        from methane.services.visit_planning import normalized

        choices, groups = normalized(selections, visit_groups)
        self._record_planning()
        results = []
        for key, start in choices:
            order = next((q for q in self.orders if q["id"] == key), None)
            try:
                plan, assessment = self.propose(key, starting_at=start)
                if not assessment["feasible"]:
                    raise ValueError("; ".join(assessment["reasons"]))
                self.executive.submit(plan)
            except (ValueError, KeyError) as exc:
                if order is not None and order["status"] == "queued":
                    order["blocked"] = str(exc)
                results.append(dict(order_id=key, accepted=False, reason=str(exc)))
                continue
            self._accepted(order, plan, self.executive.at_hour)
            results.append(dict(order_id=key, accepted=True, starting_at=plan.starting_at))
        visit_results = []
        for keys, start in groups:
            try:
                visit = accept_visit(self, keys, start)
            except (ValueError, KeyError) as exc:
                for order in self.orders:
                    if order["id"] in keys and order["status"] == "queued":
                        order["visit_blocked"] = str(exc)
                visit_results.append(dict(order_ids=list(keys), accepted=False, reason=str(exc)))
                continue
            visit_results.append(
                dict(
                    order_ids=list(keys),
                    accepted=True,
                    visit_id=visit.visit_id,
                    starting_at=visit.starting_at,
                    returning_at=visit.ending_at,
                )
            )
        if charge:
            self._charge(self.executive.at_hour, self._available_service_pv)
        charge_results = []
        for name, power_kw in charge_choices:
            try:
                plan, assessment = self.propose_charge(name, power_kw)
                if not assessment["feasible"]:
                    raise ValueError("; ".join(assessment["reasons"]))
                self.executive.submit(plan)
            except (ValueError, KeyError) as exc:
                charge_results.append(
                    dict(robot=name, requested_kw=power_kw, accepted=False, reason=str(exc))
                )
                continue
            self.interval["new_missions"].append(plan.to_dict())
            charge_results.append(
                dict(robot=name, requested_kw=power_kw, accepted=True, order_id=plan.order.order_id)
            )
        self.interval["selection"] = dict(
            implementation_id="service-selection-port/1",
            results=results,
            charging_policy="local-surplus" if charge else "deferred",
            scope="Explicit recipes rechecked against current resources; future conditions remain conditional",
        )
        if charge_requests is not None:
            self.interval["selection"].update(
                implementation_id="service-selection-port/2",
                charging_policy="explicit",
                charging=charge_results,
            )
        if groups:
            self.interval["selection"].update(
                implementation_id="service-selection-port/3",
                visit_groups=visit_results,
            )
        return self._finish_decision(projection_hours=projection_hours)

    def dispatch_local(self):
        """Preserve the existing ordered local policy and shared-visit semantics."""
        self._require_prepared()
        self._record_planning()
        hour, available_pv = self.executive.at_hour, self._available_service_pv
        if self.support:
            self.support.dispatch_visit(hour, available_pv)
        for order in self.orders:
            if order["status"] == "queued":
                self._dispatch(order, hour, available_pv)
        self._charge(hour, available_pv)
        return self._finish_decision()

    def _record_planning(self):
        """Keep original information before any selected recipe reserves work."""
        if not self.record_planning or "planning_snapshot" in self.interval:
            return
        from methane.services.snapshot import capture

        packet = capture(self)
        snapshot, definitions = packet["snapshot"], packet["catalogue"]
        self.planning_catalogues[snapshot["catalogue_id"]] = definitions
        self.interval["planning_snapshot"] = snapshot

    def _finish_decision(self, *, projection_hours=None):
        hour = self.executive.at_hour
        self.interval["electrolyser_isolated"] = self.isolation_horizon(1)[0]
        standby = self._standby or {}
        self.interval["requested_service_kwh"] = self._bus(hour) + standby.get("requested_kwh", 0)
        self.interval["decision"] = self.public()
        self.interval["decision"]["planned_missions"] = [
            {
                **m.plan.to_dict(),
                **(
                    {
                        "stochastic_event": self._effects.random_events.identity(
                            m.plan.order.order_id
                        )
                    }
                    if self._effects.random_events is not None
                    else {}
                ),
                "timeline": [
                    dict(
                        start=a,
                        end=b,
                        phase=stage.phase,
                        from_point=stage.from_point,
                        to_point=stage.to_point,
                    )
                    for a, b, stage in schedule(m.plan)
                ],
            }
            for m in self.executive.missions.values()
            if m.status in LIVE
        ]
        if projection_hours is not None:
            self.interval["decision"]["committed_demands"] = self.planned_demands(projection_hours)
        if "selection" in self.interval:
            self.interval["decision"]["selection"] = copy.deepcopy(self.interval["selection"])
        self._decision_phase = "ready"
        return self._bus(hour) + standby.get("applied_kwh", 0)

    def planned_demands(self, hours, *, candidates=()):
        """Project live cursors and optional unaccepted plans without side effects."""
        from methane.services.planning import Commitment, horizon

        if self._decision_phase not in ("prepared", "ready"):
            raise ValueError("Demand projection requires a current service decision")
        commitments = [
            Commitment(m.plan, m.stage_index, m.entered)
            for m in self.executive.missions.values()
            if m.status in LIVE
        ]
        commitments.extend(Commitment(p) for p in candidates)
        return horizon(
            commitments,
            self.executive.at_hour,
            hours,
            standby_kw=(self._standby or {}).get("applied_kwh", 0),
            isolation_resource=ISOLATION,
        )

    def begin(self, hour, diagnosis, available_pv, environment=None, *, available_battery_kw=0):
        """Compatibility entry point: prepare evidence and apply the local rule."""
        self.prepare(
            hour, diagnosis, available_pv, environment, available_battery_kw=available_battery_kw
        )
        return self.dispatch_local()

    def isolation_horizon(self, horizon):
        now = self.executive.at_hour
        return [
            any(
                b.resource == ISOLATION and overlap(b.start, b.end, now + i, now + i + 1)
                for b in self.ledger.bookings
            )
            for i in range(horizon)
        ]

    def execute_interval(self, hour, faults):
        if self._decision_phase != "ready" or self._executed or self.interval["hour"] != hour:
            raise ValueError("Service interval must execute exactly once after dispatch")
        self._effects.bind(hour, faults)
        self.executive.advance(hour + 1, self._context)
        self._executed = True
        self._decision_phase = "executed"
        events = []
        for key, mission in self.executive.missions.items():
            for event in mission.events[self._snapshots.get(key, 0) :]:
                events.append(dict(order_id=key, asset_id=mission.plan.asset.asset_id, **event))
        self.interval["mission_events"] = events
        if self.hardware or self.options.equipment_recovery_enabled:
            self.interval["hardware_execution"] = self.executive.retrospective(self._receipt_start)
        self.interval["applied_service_kwh"] = sum(
            e["bus_kwh"] for e in events if e["kind"] == "interval"
        ) + (self._standby or {}).get("applied_kwh", 0)
        self.interval["unapplied_service_kwh"] = (
            self.interval["requested_service_kwh"] - self.interval["applied_service_kwh"]
        )
        return self.interval["applied_service_kwh"]

    def end(self, hour, faults, diagnosis):
        if self._decision_phase not in ("ready", "executed"):
            raise ValueError("Service completion requires an accepted interval decision")
        if self.interval["hour"] != hour:
            raise ValueError("Service completion must match its interval")
        if not self._executed:
            self.execute_interval(hour, faults)
        record, c = self.interval, self.config
        if self.autonomy:
            record["duration_observations"] = self.executive.observed_durations()
            if self.executive._job_clock:
                clocks = self.executive._job_clock.retrospective()
                record["retrospective_job_clocks"] = {
                    p["order"]["order_id"]: clocks[p["order"]["order_id"]]
                    for p in record["new_missions"]
                    if p["order"]["order_id"] in clocks
                }
        record["retrospective_effects"] = self._effects.commit()
        if self._effects.random_events is not None:
            record["random_draws"] = self._effects.random_events.retrospective(
                self._effects._random_start
            )
        if self.options.inspection_model == "referenced-contact/1":
            record["inspection_samples"] = copy.deepcopy(self._effects.inspection_samples)
        if self.support:
            record["support_effects"] = self.support.commit(hour + 1)
        if self.cleaning_policy:
            record["cleaning_policy_effects"] = self.cleaning_policy.commit(hour + 1)
        for name, energy, boundary, source in self._effects.charge:
            accepted = self.ledger.replenish(
                Quantity("energy:" + name, energy * c.charging_efficiency, "kWh"), boundary, source
            )
            record["charge_input_kwh"] += energy
            record["charging_loss_kwh"] += energy - accepted.amount
        record["cleanings_completed"] = self._effects.cleanings
        if self.optical:
            record["surface_events"] = [
                self.optical.surface.clean(op) for op in self._effects.treatments
            ]
            self.optical.surface.advance(1)
            self.soiling = self.optical.surface.loose_mean()
            record["surface_after"] = self.optical.surface.snapshot()
            if self.autonomy:
                observed, monitor = self._reference_monitors.surface(
                    hour + 1, record["surface_after"]
                )
                record["observed_surface_after"] = observed
                record["surface_monitor_after"] = monitor
            record["brush_after_m2"] = self.ledger.stock["brush:cleaner"]
            record["treated_area_m2"] = sum(
                op["end_m2"] - op["start_m2"] for op in self._effects.treatments
            )
            record["brush_wear_m2"] = sum(
                op["end_m2"] - op["start_m2"]
                for op in self._effects.treatments
                if not op.get("method", "").startswith("portable-")
            )
        else:
            self.soiling = min(
                0.3,
                self.soiling
                * (1 - self._effects.config.cleaning_removal_fraction) ** self._effects.cleanings
                + c.soiling_per_day / 24,
            )
        for event in record["mission_events"]:
            mission = self.executive.missions[event["order_id"]]
            asset = mission.plan.asset
            if event["kind"] == "interval":
                duration = event["end"] - event["start"]
                record["robot_use_kwh"] += event["battery_kwh"]
                for name in ("cleaner", "rover", "portable"):
                    if asset.asset_id == ASSETS[name]:
                        record[name + "_hours"] += duration
                if asset.autonomy == "human" and event["phase"] in ("prepare", "perform", "verify"):
                    record["human_hours"] += duration
            if (
                event["kind"] == "stage_start"
                and event["phase"] == "travel"
                and asset.autonomy == "human"
                and (
                    event["order_id"] not in self.executive.member_visits
                    or event["at_hour"]
                    == self.executive.visits[
                        self.executive.member_visits[event["order_id"]]
                    ].starting_at
                )
            ):
                record["human_visits"] += 1
            if event["kind"] == "stage_start" and event["phase"] == "perform":
                action = mission.plan.order.action
                record["reset_attempts"] += int(action == "reset")
                record["repair_attempts"] += int(
                    action in ("module-replacement", "flow-calibration")
                )
        record["resource_events"] = copy.deepcopy(self.ledger.events[self._ledger_start :])
        if self.options.portable_cleaner != "none":
            record["water_used_l"] = sum(
                e["amount"]
                for e in record["resource_events"]
                if e["kind"] == "consume" and e["resource"] == "stock:water"
            )
            record["portable_kits_used"] = sum(
                e["amount"]
                for e in record["resource_events"]
                if e["kind"] == "consume"
                and e["resource"] == "stock:cleaning"
                and self.executive.missions[e["mission_id"]].plan.asset.asset_id
                == ASSETS["portable"]
            )
        if self.support:
            record["crew_committed_hours"] = sum(
                e["amount"]
                for e in record["resource_events"]
                if e["kind"] == "consume" and e["resource"] == "crew-hours"
            )
            record["remote_hours"] = sum(
                e["amount"]
                for e in record["resource_events"]
                if e["kind"] == "consume" and e["resource"] == "remote-hours"
            )
        if self.hardware or self.options.equipment_recovery_enabled:
            record["hardware_modules_used"] = {
                e["resource"].removeprefix("stock:hardware:"): sum(
                    x["amount"]
                    for x in record["resource_events"]
                    if x["kind"] == "consume" and x["resource"] == e["resource"]
                )
                for e in record["resource_events"]
                if e["kind"] == "consume" and e["resource"].startswith("stock:hardware:")
            }
        for event in record["resource_events"]:
            if event["kind"] == "consume":
                key = {
                    "stock:module": "service_kits_used",
                    "stock:calibration": "calibration_kits_used",
                    "stock:cleaning": "cleaning_kits_used",
                }.get(event["resource"])
                if key:
                    record[key] += event["amount"]
        self.executive.reconcile_verification(self.context(hour + 1, diagnosis))
        record.update(energy_after_kwh=self.energy, soiling_after=self.soiling, state=self.public())
        record["fixed_service_kwh"] = record["applied_service_kwh"] - record["charge_input_kwh"]
        residual = (
            sum(self.energy.values())
            - sum(record["energy_before_kwh"].values())
            - record["charge_input_kwh"]
            + record["charging_loss_kwh"]
            + record["robot_use_kwh"]
        )
        record["audits"] = [
            check("field_energy_balance", "services", residual, "kWh", interval=hour)
        ]
        if self.optical:
            consumed = sum(
                e["amount"]
                for e in record["resource_events"]
                if e["kind"] == "consume"
                and e["resource"] == "brush:cleaner"
                and self.executive.missions[e["mission_id"]].plan.order.action == "clean-section"
            )
            record["audits"].append(
                check(
                    "field_brush_coverage",
                    "services",
                    record["brush_wear_m2"] - consumed,
                    "m2",
                    interval=hour,
                )
            )
        record["audits"].append(
            check(
                "field_service_grant",
                "services",
                max(0, -record["unapplied_service_kwh"]),
                "kWh",
                interval=hour,
            )
        )
        record["audits"] += [
            check(
                "field_stock:" + r["resource"],
                "services",
                max(abs(r["residual"]), max(0, r["reserved"] - r["ending"])),
                r["unit"],
                interval=hour,
            )
            for r in self.ledger.reconcile()
        ]
        require(record["audits"], record)
        self._decision_phase = "idle"
        return copy.deepcopy(record)

    def public(self):
        telemetry = self.executive.public()
        missions = {m["order_id"]: m for m in telemetry["orders"]}
        orders = []
        for source in self.orders:
            order = copy.deepcopy(source)
            m = missions.get(order["id"])
            if m:
                status = (
                    "active"
                    if m["status"] in LIVE
                    else "verified"
                    if m["verified_at"] is not None
                    else "failed"
                    if m["status"] in ("blocked", "stranded", "invalid")
                    else m["status"]
                )
                order.update(
                    status=status,
                    phase=m["phase"],
                    progress=m["progress"],
                    completed_hour=m["completed_at"],
                    verified_at_hour=m["verified_at"],
                    reported=m["reports"][-1] if m["reports"] else None,
                    execution_status=m["status"],
                    from_point=m["from_point"],
                    to_point=m["to_point"],
                    blocked=m["reason"],
                )
                if "duration_contract" in m:
                    order["timing_evidence"] = {
                        key: copy.deepcopy(m[key])
                        for key in (
                            "progress_basis",
                            "duration_contract",
                            "observed_phase_boundaries",
                            "finish_upper_at",
                        )
                    }
                mission = self.executive.missions[order["id"]]
                if order.get("visit_id") and mission.plan.starting_at > self.executive.at_hour:
                    order.update(status="scheduled", phase="scheduled")
                order["remaining"] = max(0, mission.plan.ending_at - self.executive.at_hour)
                if self.support and order["id"] in self.support.returned:
                    order["retrieved_at"] = self.support.returned[order["id"]]["effective_at"]
                for name in ("cleaner", "rover"):
                    if m["asset_id"] == ASSETS[name]:
                        order["robot"] = name
            orders.append(order)
        robots = {}
        for name in ("cleaner", "rover"):
            key = ASSETS[name]
            state = "disabled" if key not in self.registry.assets else "available"
            if any(
                m.plan.asset.asset_id == key
                and m.status == "stranded"
                and not (self.support and self.support.recovered(m))
                for m in self.executive.missions.values()
            ):
                state = "requires retrieval"
            elif key in self.registry.assets and (
                not self.hardware_operable(name) or (self.support and not self.support.ready(name))
            ):
                state = "awaiting drive test"
            robots[name] = dict(asset_id=key, energy_kwh=self.energy[name], status=state)
        portable = None
        if self.options.portable_cleaner != "none":
            work = [q for q in orders if q["kind"] == "portable-cleaning"]
            portable = dict(
                asset_id=ASSETS["portable"],
                method=self.options.portable_cleaner,
                status="requires assistance"
                if any(
                    q.get("execution_status") == "stranded" and not q.get("retrieved_at")
                    for q in work
                )
                else "awaiting function test"
                if not self.hardware_operable("portable")
                else "working"
                if any(q["status"] == "active" for q in work)
                else "available",
                water_l=self.ledger.stock["stock:water"],
                ownership="Contracted tool; crew and resource use recorded, hire quote not yet supplied",
            )
        return dict(
            implementation_id=self.version,
            **(
                dict(uncertainty_beliefs=copy.deepcopy(self.belief_record))
                if self.belief_record
                else {}
            ),
            **(
                {
                    "hardware": {
                        "implementation_id": self.hardware_model,
                        "observations": self.hardware.public(),
                        "recovery_enabled": self.options.equipment_recovery_enabled,
                    }
                }
                if self.hardware
                else {}
            ),
            inspection=self.inspection_evidence(),
            portable=portable,
            support=self.support.public() if self.support else None,
            surface=getattr(self.optical, "planning_surface", self.optical.surface).public()
            if self.optical
            else None,
            robots=robots,
            soiling_estimate=getattr(
                self.optical, "planning_surface", self.optical.surface
            ).loose_mean()
            if self.optical
            else self.soiling,
            soiling_sensor="bounded removable-surface monitor; last decision observation"
            if self.autonomy and self.optical
            else "ideal section surface monitor"
            if self.optical
            else "ideal lumped-loss monitor",
            orders=orders,
            service_kits=self.ledger.stock["stock:module"],
            cleaning_kits=self.ledger.stock["stock:cleaning"],
            calibration_kits=self.ledger.stock["stock:calibration"],
            executive=telemetry,
            **({"cleaning_policy": self.cleaning_policy.public()} if self.cleaning_policy else {}),
            **(
                {
                    "inspection_interface": {
                        "implementation_id": "contact-access/1",
                        "kind": self.options.inspection_interface,
                        "accessible": self.options.inspection_interface == "accessible-port",
                        "scope": "Known plant interface compatibility for the contact payload. Enclosed contacts require a different intervention; no visual diagnosis is inferred.",
                    }
                }
                if self.options.inspection_interface != "legacy-prepared"
                else {}
            ),
            **({"standby": copy.deepcopy(self._standby)} if self._standby is not None else {}),
        )

    def inspection_evidence(self):
        if self.options.inspection_model != "referenced-contact/1":
            return None
        from methane.services.inspection import evidence

        return evidence(
            Context(
                self.executive.at_hour,
                (*self.executive.observations(), *self.contact_changes(self.executive.at_hour)),
            ),
            self.options,
            self.orders,
            commissioned_only=getattr(self, "_capacity_request_policy", "local") == "investigation",
        )

    def contact_changes(self, hour):
        # Known work invalidates an earlier contact sample whether or not that
        # work physically succeeded. The supervisor never sees effect truth.
        completed = [
            m.work_completed_at
            for m in self.executive.missions.values()
            if m.plan.order.action in ("reset", "module-replacement")
            and m.work_completed_at is not None
            and available_boundary(m.work_completed_at) <= hour
        ]
        return (
            (
                Reading(
                    "contact-evidence-cutoff",
                    max(completed),
                    "h",
                    hour,
                    hour,
                    "recorded-contact-procedure/1",
                ),
            )
            if completed
            else ()
        )

    def observed_module_procedures(self):
        """Eligible attempted-work notifications; no physical receipt contents.

        Work completion can precede mission return. It does not report whether
        a procedure restored hardware, and cannot authorise an operating test
        before the separate work/return reservations permit it.
        """
        from methane.services.recovery_belief import Procedure

        return tuple(
            Procedure(m.plan.order.order_id, m.plan.order.action, m.work_completed_at)
            for m in self.executive.missions.values()
            if m.plan.order.action in ("reset", "module-replacement")
            and m.work_completed_at is not None
            and available_boundary(m.work_completed_at) <= self.executive.at_hour
        )
