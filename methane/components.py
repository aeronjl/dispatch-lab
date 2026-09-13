"""Explicit plant assembly adapters. Pure component kernels never import this module."""

from dataclasses import asdict, dataclass

from methane import battery, electrolyser, reactor, storage


@dataclass(frozen=True)
class Components:
    battery: battery.Battery
    electrolyser: electrolyser.Electrolyser
    hydrogen: storage.Storage
    co2: storage.Storage
    reactor: reactor.Reactor

    def identities(self):
        return {
            key: getattr(self, key).identity()
            for key in ("battery", "electrolyser", "hydrogen", "co2", "reactor")
        }


def assemble(p, models=None, battery_override=None):
    def choose(key, default):
        return getattr(models, key, default) if models is not None else default

    return Components(
        battery_override or battery.from_plant(p, choose("battery", "affine/1")),
        electrolyser.from_plant(p, choose("electrolyser", "specific-energy/1")),
        storage.from_plant(p, "hydrogen", choose("hydrogen", "balance/1")),
        storage.from_plant(p, "co2", choose("co2", "balance/1")),
        reactor.from_plant(p, choose("reactor", "analytic/1")),
    )


def record(component, before, inputs, result):
    return {
        "schema_version": "dispatch-lab/component-record/1",
        **component.identity(),
        "parameters": asdict(component.parameters),
        "before": asdict(before),
        "inputs": asdict(inputs),
        "after": asdict(result.state),
        "flows": dict(result.flows),
        "diagnostics": dict(result.diagnostics),
        "audits": list(result.audits),
    }
