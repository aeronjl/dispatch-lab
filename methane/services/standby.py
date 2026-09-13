"""Hourly dock-control demand, granted before discretionary process consumption."""

from dataclasses import replace
from math import isfinite

from methane.services.contracts import Requirement
from methane.services.registry import Registry

VERSION = "dock-standby/1"


def extend(base):
    requirement = Requirement("dock-control-powered", "equals", True, "boolean", 1)
    caps = [
        replace(c, requirements=(*c.requirements, requirement))
        if c.action.startswith("charge-") or c.capability_id == "hardware-test:dock"
        else c
        for c in base.capabilities.values()
    ]
    return Registry(
        list(base.assets.values()),
        list(base.interfaces.values()),
        caps,
        list(base.resources.values()),
        base.access,
    )


def allocate(demand_kw, pv_kw, battery_available_kw, installed):
    if not isinstance(installed, bool):
        raise ValueError("Installed dock flag must be boolean")
    for v in (demand_kw, pv_kw, battery_available_kw):
        if isinstance(v, bool) or not isfinite(v) or v < 0:
            raise ValueError("Standby demand and available power must be finite and nonnegative")
    requested = demand_kw if installed else 0
    # The control board needs its complete declared rate. A brownout does not
    # earn a fraction of an operational hour or a partially working charger.
    supplied = requested if requested <= pv_kw + battery_available_kw + 1e-9 else 0
    return dict(
        implementation_id=VERSION,
        requested_kwh=requested,
        applied_kwh=supplied,
        unserved_kwh=requested - supplied,
        pv_available_kw=pv_kw,
        battery_available_kw=battery_available_kw,
        installed=installed,
        control_available=bool(installed and supplied == requested),
        scope="One-hour constant control-electronics load upstream of the charger power stage. Full-rate priority grant; active service remains solar-only. A failed charger can still consume control standby power.",
    )
