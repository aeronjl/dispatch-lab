"""Named service outcome draws, independent of editorial and scheduling details.

Registration follows accepted requests, not candidate evaluation or random draw
order. The ledger is private execution state. Only event identities are public;
realised variates belong in retrospective truth, never controller observations.
"""

import copy
import hashlib
import json
from dataclasses import asdict, dataclass

from methane.services.contracts import identifier, nonnegative

LEGACY = "legacy-reason/1"
VERSION = "target-action-request/1"


@dataclass(frozen=True)
class Event:
    target: str
    action: str
    request: int
    model: str = VERSION

    def __post_init__(self):
        identifier(self.target, "event target")
        identifier(self.action, "event action")
        if type(self.request) is not int or self.request < 1:
            raise ValueError("Event request must be a positive integer")
        if self.model != VERSION:
            raise ValueError("Unknown service random event model")

    def to_dict(self):
        return asdict(self)


def uniform(seed, event, channel):
    """Exact binary fraction from the first 53 SHA-256 bits, always below one."""
    if type(seed) is not int or seed < 0:
        raise ValueError("Service event seed must be a nonnegative integer")
    identifier(channel, "event channel")
    token = [VERSION, seed, event.target, event.action, event.request, channel]
    encoded = json.dumps(token, ensure_ascii=True, separators=(",", ":")).encode()
    bits = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big") >> 11
    return bits / 2**53


class Events:
    def __init__(self, seed):
        if type(seed) is not int or seed < 0:
            raise ValueError("Service event seed must be a nonnegative integer")
        self.seed = seed
        self._requests, self._events, self._draws, self._records = {}, {}, {}, []

    def register(self, order_id, target, action):
        identifier(order_id, "order")
        identifier(target, "event target")
        identifier(action, "event action")
        existing = self._events.get(order_id)
        if existing is not None:
            if (existing.target, existing.action) != (target, action):
                raise ValueError("An accepted order cannot change its random event identity")
            return existing
        key = (target, action)
        event = Event(target, action, self._requests.get(key, 0) + 1)
        self._requests[key] = event.request
        self._events[order_id] = event
        return event

    def identity(self, order_id):
        event = self._events.get(order_id)
        return event.to_dict() if event is not None else None

    def draw(self, plan, channel, at_hour):
        nonnegative(at_hour, "draw interval")
        event = self._events.get(plan.order.order_id)
        if event is None:
            raise ValueError("Register an accepted service request before drawing its outcome")
        if (event.target, event.action) != (plan.interface.target_asset_id, plan.order.action):
            raise ValueError("Mission does not match its registered random event")
        key = (plan.order.order_id, channel)
        if key not in self._draws:
            value = uniform(self.seed, event, channel)
            self._draws[key] = value
            self._records.append(
                dict(
                    order_id=plan.order.order_id,
                    event=event.to_dict(),
                    channel=channel,
                    uniform=value,
                    first_used_hour=at_hour,
                )
            )
        return self._draws[key]

    @property
    def count(self):
        return len(self._records)

    def retrospective(self, start=0):
        return copy.deepcopy(self._records[start:])
