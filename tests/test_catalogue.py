from methane.catalogue import catalogue
from methane.contracts import SPECS


def test_all_registered_components_describe_execution_planning_and_evidence():
    for spec in SPECS.values():
        assert spec.execution_interface and spec.planning_interface and spec.verification
        assert spec.assumptions and spec.time_semantics
    entries = catalogue()["components"]
    for key in ("battery", "electrolyser", "hydrogen", "co2", "reactor"):
        assert entries[key]["planning_ports"]
        assert all(p["unit"] and p["timing"] for p in entries[key]["planning_ports"])
        assert entries[key]["planning_constraints"]
