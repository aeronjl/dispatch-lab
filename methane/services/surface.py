"""Piecewise array surface inventory and compatible partial treatment.

No navigation, panel-string or empirical weather-removal model. Areas and loss
fractions are distinct: dry brushing removes loose material only; explicitly
wet treatment can also remove its declared adhered fraction. The solar
kernel uses area-mean transmission for its existing lumped section temperature.
"""

import copy
from dataclasses import asdict, dataclass
from math import isfinite

VERSION = "array-surface/1"


@dataclass(frozen=True)
class Patch:
    start_m2: float
    end_m2: float
    removable: float
    adhered: float
    damaged: float

    def __post_init__(self):
        if not all(isfinite(x) for x in vars(self).values()):
            raise ValueError("Surface inputs must be finite")
        if not 0 <= self.start_m2 < self.end_m2 or not all(
            0 <= x <= 1 for x in (self.removable, self.adhered, self.damaged)
        ):
            raise ValueError("Invalid patch area or optical loss fraction")

    @property
    def area(self):
        return self.end_m2 - self.start_m2

    @property
    def transmission(self):
        return (1 - self.removable) * (1 - self.adhered) * (1 - self.damaged)


def treat(patches, start, end, efficacy_start, efficacy_end, adhered_removal=0):
    """Treat one contiguous, previously traversed area; linear brush efficacy.

    Each intersected patch uses the exact average of the linearly changing
    efficacy. Constant-efficacy sweeps are invariant to integration boundaries;
    subsequent overlapping sweeps of a varying-efficacy patch use its stored
    area mean. The plant adapter freezes efficacy for each pass. Adhered removal
    is a separate constant input, zero for dry brushing. Damage is unchanged.
    """
    if (
        not 0 <= start < end <= patches[-1].end_m2 + 1e-8
        or not 0 <= adhered_removal <= 1
        or not 0 <= min(efficacy_start, efficacy_end) <= max(efficacy_start, efficacy_end) <= 1
    ):
        raise ValueError("Treatment exceeds section bounds or declared efficacy")
    out = []
    for p in patches:
        edges = sorted(
            {
                p.start_m2,
                p.end_m2,
                max(p.start_m2, min(p.end_m2, start)),
                max(p.start_m2, min(p.end_m2, end)),
            }
        )
        for a, b in zip(edges, edges[1:], strict=False):
            removal = 0
            if a < end and b > start:
                midpoint = (a + b) / 2
                removal = efficacy_start + (efficacy_end - efficacy_start) * (midpoint - start) / (
                    end - start
                )
            attached = p.adhered * (1 - adhered_removal) if a < end and b > start else p.adhered
            out.append(Patch(a, b, p.removable * (1 - removal), attached, p.damaged))
    return tuple(out)


class Surface:
    def __init__(self, capacities, config, options):
        self.version = "array-surface/2" if options.portable_cleaner != "none" else VERSION
        self.sections = {}
        for i, kw in enumerate(capacities):
            if kw > 0:
                self.sections[f"PV-{i + 1:02d}"] = (
                    Patch(
                        0,
                        kw * options.area_m2_per_kw,
                        config.initial_soiling_fraction,
                        options.initial_adhered_fraction,
                        options.initial_damage_fraction,
                    ),
                )
        self.accumulation_per_hour = config.soiling_per_day / 24
        self.events = []
        self.initial_state = self.snapshot()

    def snapshot(self):
        return {key: [asdict(p) for p in patches] for key, patches in self.sections.items()}

    def section(self, key):
        patches = self.sections[key]
        area = patches[-1].end_m2
        return dict(
            id=key,
            area_m2=area,
            removable_fraction=sum(p.removable * p.area for p in patches) / area,
            adhered_fraction=sum(p.adhered * p.area for p in patches) / area,
            damage_fraction=sum(p.damaged * p.area for p in patches) / area,
            transmission=sum(p.transmission * p.area for p in patches) / area,
            patches=[asdict(p) for p in patches],
        )

    def public(self):
        return dict(
            model=self.version,
            sections=[self.section(k) for k in self.sections],
            observation_basis="Ideal section surface monitor; loose/adhered/damaged fractions are assumed observable in this fixture",
        )

    def loose_mean(self):
        rows = [self.section(k) for k in self.sections]
        area = sum(r["area_m2"] for r in rows)
        return sum(r["area_m2"] * r["removable_fraction"] for r in rows) / area if area else 0

    def clean(self, operation):
        op = copy.deepcopy(operation)
        key = op["section"]
        before = self.section(key)
        method = op.get("method", "dry-brush")
        if method not in ("dry-brush", "portable-dry", "portable-wet"):
            raise ValueError("Unsupported surface treatment")
        if method != "portable-wet" and op.get("adhered_removal", 0):
            raise ValueError("Dry brushing cannot remove adhered material")
        self.sections[key] = treat(
            self.sections[key],
            op["start_m2"],
            op["end_m2"],
            op["efficacy_start"],
            op["efficacy_end"],
            op.get("adhered_removal", 0),
        )
        after = self.section(key)
        event = {**op, "before": before, "after": after, "kind": method}
        self.events.append(event)
        return event

    def advance(self, hours):
        if not isfinite(hours) or hours < 0:
            raise ValueError("Invalid accumulation interval")
        for key, patches in self.sections.items():
            self.sections[key] = tuple(
                Patch(
                    p.start_m2,
                    p.end_m2,
                    min(0.3, p.removable + self.accumulation_per_hour * hours),
                    p.adhered,
                    p.damaged,
                )
                for p in patches
            )

    def design(self, baseline, offset=0):
        """No future cleaning is assumed. Existing design soiling remains separate."""
        value = copy.deepcopy(baseline)
        for i, section in enumerate(value["sections"]):
            patches = self.sections.get(f"PV-{i + 1:02d}", ())
            if patches:
                area = patches[-1].end_m2
                trans = (
                    sum(
                        (1 - min(0.3, p.removable + self.accumulation_per_hour * offset))
                        * (1 - p.adhered)
                        * (1 - p.damaged)
                        * p.area
                        for p in patches
                    )
                    / area
                )
                section["soiling"] = 1 - (1 - section["soiling"]) * trans
        return value
