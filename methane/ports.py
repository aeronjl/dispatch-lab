"""Solver-independent component ports and immutable linear planning fragments."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Port:
    name: str
    unit: str
    meaning: str
    timing: str = "interval mean rate or interval total; state at interval end"


@dataclass(frozen=True)
class LinearRow:
    """Terms are (local port, interval index, coefficient)."""

    name: str
    terms: tuple[tuple[str, int, float], ...]
    lower: float
    upper: float


@dataclass(frozen=True)
class PlanningBlock:
    bounds: tuple[tuple[str, float, float, bool], ...]
    rows: tuple[LinearRow, ...]
    ports: tuple[Port, ...] = ()


def equality(name, terms, value=0):
    return LinearRow(name, tuple(terms), value, value)


def on_start_rows(power, on, start, t, minimum, maximum, prior):
    """Exact on/start truth table plus turndown, with prior state at t=0."""
    return (
        LinearRow("maximum_power", ((power, t, 1), (on, t, -maximum)), -float("inf"), 0),
        LinearRow("minimum_power", ((power, t, 1), (on, t, -minimum)), 0, float("inf")),
        LinearRow("start_requires_on", ((start, t, 1), (on, t, -1)), -float("inf"), 0),
        LinearRow(
            "off_to_on_starts",
            tuple([(on, t, 1), (start, t, -1)] + ([(on, t - 1, -1)] if t else [])),
            -float("inf"),
            int(prior) if not t else 0,
        ),
        LinearRow(
            "already_on_not_start",
            tuple([(start, t, 1)] + ([(on, t - 1, 1)] if t else [])),
            -float("inf"),
            1 - int(prior) if not t else 1,
        ),
    )
