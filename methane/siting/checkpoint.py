"""Versioned execution checkpoints. Never a controller observation or a pickle.

Only data instances from the enumerated production modules can be restored. The
source identity, weather and policy bindings must match before decoding. Shared
references (notably the optical surface and service ledger) are retained.
"""

import importlib
import math
from dataclasses import dataclass

from methane.siting.store import digest

VERSION = "dispatch-lab/simulation-checkpoint/1"
MODULES = (
    "plant methane.config methane.physics methane.sensing methane.faults "
    "methane.field_operations methane.adaptation methane.autonomy methane.recovery "
    "methane.battery methane.electrolyser methane.storage methane.reactor "
    "methane.services.plant methane.services.configuration methane.services.contracts "
    "methane.services.resources methane.services.executive methane.services.access "
    "methane.services.support methane.services.hardware methane.services.maintenance "
    "methane.services.local_policy methane.services.surface methane.services.optical "
    "methane.services.randomness methane.services.job_clock methane.services.uncertain_timing "
    "methane.services.controller methane.services.verification methane.services.investigator "
    "methane.services.investigation_belief methane.services.recovery_belief "
    "methane.services.joint_recovery methane.services.recovery_loop "
    "methane.services.charging methane.services.charge_control methane.services.registry methane.services.weather_recovery methane.services.obligation_recovery methane.services.continuation"
).split()
FIELDS = (
    "state observation diagnosis physical_faults services physical_optical observer "
    "service_controller recovery_scheduler joint_recovery_scheduler previous_recovery previous_issue service_cost_rows"
).split()


def classes():
    result = {}
    for name in MODULES:
        module = importlib.import_module(name)
        for key, value in vars(module).items():
            if isinstance(value, type) and value.__module__ == name:
                result[name + ":" + key] = value
    return result


def pack(value):
    nodes, seen, allowed = [], {}, classes()

    def visit(item):
        if item is None or type(item) in (str, int, bool):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("Nonfinite checkpoint value")
            return item
        import numpy as np

        if isinstance(item, np.generic):
            return visit(item.item())
        from methane.services.adapters import BUILDERS

        builder = next((k for k, v in BUILDERS.items() if item is v), None)
        if builder is not None:
            return {"builder": builder}
        key = id(item)
        if key in seen:
            return {"ref": seen[key]}
        index = len(nodes)
        seen[key] = index
        node = {}
        nodes.append(node)
        if isinstance(item, dict):
            node.update(kind="dict", items=[[visit(k), visit(v)] for k, v in item.items()])
        elif type(item) in (list, tuple, set, frozenset):
            node.update(kind=type(item).__name__, items=[visit(v) for v in item])
        elif isinstance(item, np.ndarray):
            node.update(kind="array", items=visit(item.tolist()), dtype=str(item.dtype))
        else:
            name = type(item).__module__ + ":" + type(item).__name__
            if name not in allowed or not hasattr(item, "__dict__"):
                raise ValueError(f"Unsupported checkpoint type: {name}")
            node.update(
                kind="instance", class_id=name, fields={k: visit(v) for k, v in vars(item).items()}
            )
        return {"ref": index}

    root = visit(value)
    return {"root": root, "nodes": nodes}


def unpack(graph):
    allowed, cache = classes(), {}
    nodes = graph["nodes"]
    if len(nodes) > 1_000_000:
        raise ValueError("Checkpoint exceeds node budget")

    def visit(item):
        if not isinstance(item, dict):
            return item
        if "builder" in item:
            from methane.services.adapters import BUILDERS

            if item["builder"] not in BUILDERS:
                raise ValueError("Unknown service builder")
            return BUILDERS[item["builder"]]
        index = item["ref"]
        if type(index) is not int or not 0 <= index < len(nodes):
            raise ValueError("Invalid checkpoint reference")
        if index in cache:
            return cache[index]
        node = nodes[index]
        kind = node["kind"]
        if kind == "instance":
            cls = allowed.get(node["class_id"])
            if cls is None:
                raise ValueError("Unknown checkpoint class")
            obj = object.__new__(cls)
            cache[index] = obj
            obj.__dict__.update({k: visit(v) for k, v in node["fields"].items()})
        elif kind == "dict":
            obj = cache[index] = {}
            obj.update((visit(k), visit(v)) for k, v in node["items"])
        elif kind in ("list", "tuple", "set", "frozenset"):
            obj = cache[index] = []
            obj.extend(visit(v) for v in node["items"])
            obj = {"list": list, "tuple": tuple, "set": set, "frozenset": frozenset}[kind](obj)
            cache[index] = obj
        elif kind == "array":
            import numpy as np

            if node["dtype"] not in ("float64", "float32", "int64", "int32", "bool"):
                raise ValueError("Unsupported checkpoint array type")
            obj = cache[index] = np.asarray(visit(node["items"]), dtype=node["dtype"])
        else:
            raise ValueError("Unknown checkpoint node kind")
        return obj

    return visit(graph["root"])


@dataclass
class Continuation:
    total_hours: int
    stop_hour: int
    binding: str
    checkpoint: dict | None = None
    initial: dict | None = None
    output: dict | None = None
    utilities: dict | None = None

    @property
    def start_hour(self):
        return self.checkpoint["next_hour"] if self.checkpoint else 0

    def restore(self):
        if not 0 <= self.start_hour < self.stop_hour <= self.total_hours <= 8784 * 40:
            raise ValueError("Invalid chronological execution interval")
        if not self.checkpoint:
            return None
        value = self.checkpoint
        if value["schema_version"] != VERSION or value["binding"] != self.binding:
            raise ValueError("Checkpoint source/config/weather/policy binding mismatch")
        if value["graph_sha256"] != digest(value["graph"]):
            raise ValueError("Checkpoint state integrity mismatch")
        return unpack(value["graph"])

    def capture(self, next_hour, scope):
        graph = pack({**{k: scope[k] for k in FIELDS}, "previous_row": scope["rows"][-1]})
        self.output = dict(
            schema_version=VERSION,
            binding=self.binding,
            next_hour=next_hour,
            graph=graph,
            graph_sha256=digest(graph),
            scope="Retrospective execution runtime; never supplied to dispatch or diagnosis",
        )
