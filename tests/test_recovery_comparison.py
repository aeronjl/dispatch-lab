import copy
from dataclasses import replace

import pytest

from methane.recovery_comparison import CONDITIONS, fixture, specification
from methane.uncertainty_studies import resolve_cases


def test_comparison_arms_match_physical_worlds_and_keep_null_exact():
    for condition in CONDITIONS:
        c = fixture(condition)
        worlds = []
        for arm in ("fixed", "adaptive", "risk-aware"):
            spec = specification(c, condition, arm, (7, 17, 29))
            cases = resolve_cases(spec, c.to_dict(), "reference")
            assert all(x["input_error"] is None for x in cases)
            assert len(cases) == 3
            worlds.append([x["config"] for x in cases])
        assert worlds[0] == worlds[1] == worlds[2]
    c = fixture("null")
    assert c.field_operations.mission_failure_probability == 0
    spec = specification(c, "null", "risk-aware", (7,))
    assert spec["uncertainty"]["autonomy"]["weather_factors"] == [1]


def test_historical_prefix_preserves_raw_data_and_availability(monkeypatch):
    from methane import weather
    from methane.studies import uncertainty_weather_input

    c = fixture("persistent-damage")
    c = replace(c, weather=replace(c.weather, mode="historical", offline=True))
    original = dict(
        times=[f"hour{i}" for i in range(240)],
        snapshots=[{"id": "saved-raw"}],
        vintages=[{"available_at": "2026-07-10T06:00Z"}],
        truth={"original": "unaltered"},
    )

    def prepare(config):
        assert config.scenario.hours == 240 and config.weather.offline
        return copy.deepcopy(original)

    monkeypatch.setattr(weather, "prepare", prepare)
    result = uncertainty_weather_input(c, {"weather_source_hours": 240})
    assert result["times"] == original["times"][:48]
    assert result["snapshots"] == original["snapshots"]
    assert result["vintages"] == original["vintages"]
    assert result["truth"] == original["truth"]
    with pytest.raises(ValueError, match="cover"):
        uncertainty_weather_input(c, {"weather_source_hours": 24})
    with pytest.raises(ValueError, match="historical"):
        uncertainty_weather_input(fixture("null"), {"weather_source_hours": 240})
