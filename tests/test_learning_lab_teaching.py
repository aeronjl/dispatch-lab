import pytest

from methane.learning import evaluate


@pytest.mark.parametrize("hour,delay", [(0, 6), (2, 2), (6, 0)])
def test_teaching_publication_boundary_has_independent_expected_value(hour, delay):
    value = evaluate("learning_data", dict(hour=hour, delay=delay))
    assert value["status"] == "complete"
    assert value["metrics"][0]["value"] == int(hour >= delay)
    rejected = evaluate("learning_data", dict(overlap="yes"))
    assert rejected["metrics"][1]["value"] == 0
    assert "Leakage" in rejected["scope"]


@pytest.mark.parametrize("task", ["pv", "soiling", "solar_condition", "electrolyser_condition"])
def test_estimator_lessons_are_real_calculations_with_reproducible_inputs(task):
    value = evaluate("estimators", dict(task=task))
    assert value["status"] == "complete"
    assert value["evaluation"]["status"] == "complete"
    assert value["evaluation"]["rows_per_split"]["test"] > 0
    repeated = evaluate("estimators", dict(task=task))
    assert repeated == value


def test_reserve_lesson_exposes_preferences_solver_limitations_and_zero_value():
    value = evaluate("policies", dict(price=0, power=0, weight=5))
    assert value["status"] == "complete"
    for run in value["steps"]:
        assert run["plan"]["solver"]["status"] in (
            "solved",
            "fallback",
            "time-limited",
            "local-rule",
        )
        if run["reserves"]:
            assert run["reserves"]["preference_penalty"] >= 0
