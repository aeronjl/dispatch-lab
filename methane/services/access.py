"""Declared access graph, with observation-gated edges and platform compatibility."""

import heapq
from dataclasses import dataclass

from methane.services.contracts import Requirement, identifier, nonnegative


@dataclass(frozen=True)
class Edge:
    edge_id: str
    origin: str
    destination: str
    hours: float
    mobility: tuple[str, ...]
    requirements: tuple[Requirement, ...] = ()
    resource_id: str | None = None

    def __post_init__(self):
        for key in ("edge_id", "origin", "destination"):
            identifier(getattr(self, key), key)
        nonnegative(self.hours, "edge travel time")
        if not self.hours or self.origin == self.destination:
            raise ValueError("Access edge needs distinct points and positive travel time")


class Access:
    def __init__(self, edges):
        self.edges = tuple(edges)
        if len({e.edge_id for e in self.edges}) != len(self.edges):
            raise ValueError("Duplicate access edge")

    def route(self, origin, destination, mobility, context):
        """Shortest declared eligible route; ties resolve by stable edge identifiers."""
        queue, visited = [(0.0, (), origin)], set()
        by_id = {e.edge_id: e for e in self.edges}
        while queue:
            duration, ids, point = heapq.heappop(queue)
            if point == destination:
                return tuple(by_id[key] for key in ids)
            if point in visited:
                continue
            visited.add(point)
            for edge in sorted(self.edges, key=lambda e: e.edge_id):
                if edge.origin != point or mobility not in edge.mobility:
                    continue
                if any(r.failure(context) for r in edge.requirements):
                    continue
                heapq.heappush(
                    queue, (duration + edge.hours, (*ids, edge.edge_id), edge.destination)
                )
        raise ValueError(f"No eligible {mobility} route from {origin} to {destination}")
