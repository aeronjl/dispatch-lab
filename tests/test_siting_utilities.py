from test_siting_production import fixture

from methane.siting.production import create, execute, inspect, load_period
from methane.siting.store import Store
from methane.siting.utilities import Utilities


def test_disclosed_water_limit_and_delivery_calendar_reach_execution(tmp_path):
    store = Store(tmp_path)
    d, e = fixture(store, 18)
    design = store.get("design", d)
    design["utilities"] = Utilities(
        water_lph=0, co2_deliveries=[{"hour": 13, "kg": 800}]
    ).model_dump(mode="json")
    d = store.put("design", design)
    s = create(
        store, name="Finite supply", cases=[dict(design_id=d, environment_id=e)], partition_hours=9
    )
    execute(store, s["id"])
    case = inspect(store, s["id"])["cases"][0]
    assert case["summary"]["h2_produced_kg"] == 0
    rows = [
        r
        for p in case["periods"]
        for r in load_period(store, p["period_sha256"])["records"]["Greedy"]
    ]
    assert all(r["site_utilities"]["water_consumed_l"] == 0 for r in rows)
    assert rows[13]["co2_delivered_kg"] == 500 and rows[13]["co2_rejected_kg"] == 300
    assert sum(r["co2_delivered_kg"] for r in rows) == 500
    assert rows[12]["decision"]["forecast"]["deliveries_kg"][1] == 800
