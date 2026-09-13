"""Private matched per-job clocks, committed only after resource acceptance."""

import copy

from methane.services.randomness import Event, uniform


class JobClock:
    def __init__(self, model, factors, seed):
        self.model, self.factors, self.seed = copy.deepcopy(model), dict(factors), seed
        self.counts, self.records = {}, {}

    def prepare(self, plans):
        counts, records = dict(self.counts), {}
        for plan in plans:
            target, action = plan.interface.target_asset_id, plan.order.action
            key = (target, action)
            event = Event(target, action, counts.get(key, 0) + 1)
            counts[key] = event.request
            factors, draws = {}, {}
            for group, item in self.model["groups"].items():
                persistent = self.factors[group]
                if persistent not in item["persistent_factors"]:
                    raise ValueError(
                        "Actual persistent equipment clock is outside the declared grid"
                    )
                u = uniform(self.seed, event, "duration:" + group)
                a, b = item["job_multiplier_bounds"]
                job = a + (b - a) * u
                factors[group] = persistent * job
                draws[group] = dict(
                    uniform=u,
                    persistent_factor=persistent,
                    job_multiplier=job,
                    applied_factor=factors[group],
                )
            records[plan.order.order_id] = dict(
                event=event.to_dict(),
                asset_id=plan.asset.asset_id,
                factors=factors,
                draws=draws,
                model=self.model["version"],
            )
        return counts, records

    def commit(self, prepared):
        self.counts, records = prepared
        self.records.update(records)

    def retrospective(self):
        return copy.deepcopy(self.records)
