"""Small, explicitly constructed observation fixtures; not plant calibration."""

import random
from dataclasses import asdict

from methane.config import Costs, Plant
from methane.learning_lab.datasets import packet, save, validate_splits
from methane.siting.store import digest


def teaching_dataset(store, seed=7, noise=0.01, missing=False):
    rng = random.Random(seed)
    episodes, samples, labels = [], [], []
    plant, prices = asdict(Plant()), asdict(Costs())
    for month, split in enumerate(("train", "validation", "test"), 1):
        eid = digest(["constructed-observation-fixture/1", seed, split])
        episodes.append(
            dict(
                id=eid,
                split=split,
                site="teaching-site",
                design="teaching-design",
                equipment=digest(plant),
                start=f"2025-{month:02}-01T00:00:00Z",
                end=f"2025-{month:02}-02T00:00:00Z",
                seed=seed,
                repetition=1,
                source="constructed-observation-fixture/1",
                config={"plant": plant, "costs": prices},
                partitions=[],
                reference="Constructed assumed meter channels, not operating plant observations",
            )
        )
        for h in range(24):
            # Repeated activity distribution across held-out episodes makes a
            # checkable identity map while noise remains independently seeded.
            pv = 50 + (h % 6) * 40
            condition = 0.02 + h * 0.001 + rng.uniform(-noise, noise)
            d = dict(
                hour=h,
                observations={"power_kw": 100 + (h % 4) * 20},
                forecast={"pv_kw": [pv, 50 + ((h + 1) % 6) * 40], "ambient_c": [20, 20]},
                lifecycle={
                    "condition": {
                        a: {
                            "measurement": dict(
                                value=max(0, condition),
                                measured_at=h,
                                available_at=h,
                                source="assumed-channel",
                                noise_bound=noise,
                            )
                        }
                        for a in ("solar", "electrolyser")
                    }
                },
                field_operations={
                    "soiling_estimate": max(0, condition),
                    "soiling_sensor": "assumed surface monitor",
                },
            )
            if missing and h % 3 == 0:
                d["lifecycle"]["condition"] = {}
            p = packet(d, time=f"2025-{month:02}-01T{h:02}:00:00Z", prices=prices, plant=plant)
            sid = digest([eid, h])
            samples.append(dict(id=sid, episode=eid, split=split, packet=p, packet_id=digest(p)))
            labels.append(
                dict(id=sid, basis="Constructed fixture; no plant truth", value=condition)
            )
    validate_splits(episodes)
    return save(store, "Constructed observation lesson", episodes, samples, labels)
