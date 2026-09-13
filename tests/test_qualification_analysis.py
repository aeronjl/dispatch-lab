import copy

import pytest

from methane.qualification_analysis import compact, comparisons, numerical_spreads


def record():
    return dict(
        study_id="study",
        case_id="case-1",
        source="source",
        controller="MPC · methane",
        environment_id="weather",
        group="null",
        label=dict(pair="normal", seed=7, repetition=1, arm="reference"),
        physical_trace_hash="trace",
        config={"plant": {"electrolyser_kw": 450}},
        executed_policy={"objective": "methane"},
        summary={"methane_kg": 10, "capacity_confirmed_hour": None},
        hours=2,
        expected_hours=2,
        periods=[],
        timeline=[
            dict(
                truth_capacity_kw=225,
                human_hours=0,
                human_visits=0,
                remote_hours=0,
                diagnosis={"capacity_kw": 225},
            ),
            dict(
                truth_capacity_kw=450,
                human_hours=2,
                human_visits=1,
                remote_hours=0,
                diagnosis={"capacity_kw": 225},
            ),
        ],
    )


def test_physical_repair_is_not_observer_confirmation_or_robotic_repair():
    r = record()
    v = compact(r)
    assert v["outcome"] == "Physical restoration; not confirmed"
    assert v["human_hours"] == 2
    assert v["human_visits"] == 1
    r["summary"]["capacity_confirmed_hour"] = 2
    assert compact(r)["outcome"] == "Restored and confirmed"
    r["hours"] = 1
    assert compact(r)["outcome"] == "Incomplete exposure"


def test_comparison_discloses_confounds_and_does_not_fill_missing_outcomes():
    a = record()
    b = copy.deepcopy(a)
    b["case_id"] = "case-2"
    b["label"]["arm"] = "alternative"
    b["config"]["plant"]["electrolyser_kw"] = 600
    b["environment_id"] = "other-weather"
    b["summary"]["methane_kg"] = 14
    delta = comparisons([a, b])[0]
    assert delta["deltas"]["methane_kg"] == 4
    assert delta["deltas"]["capacity_confirmed_hour"] is None
    assert delta["changed_config_paths"] == ["plant.electrolyser_kw"]
    assert not delta["same_environment"]
    b["summary"] = None
    assert comparisons([a, b])[0]["deltas"]["methane_kg"] is None


def test_numerical_repeats_require_identical_information_and_distinct_repetitions():
    a = record()
    b = copy.deepcopy(a)
    b["label"]["repetition"] = 2
    b["summary"]["methane_kg"] = 12
    b["physical_trace_hash"] = "different"
    spread = numerical_spreads([a, b])[0]
    assert spread["spreads"]["methane_kg"] == 2
    assert not spread["exact_physical_trace_identity"]
    b["environment_id"] = "different"
    with pytest.raises(ValueError, match="different frozen"):
        numerical_spreads([a, b])
    b["environment_id"] = a["environment_id"]
    b["label"]["repetition"] = 1
    with pytest.raises(ValueError, match="Duplicate"):
        numerical_spreads([a, b])


def test_full_recovery_requires_more_than_the_first_load_step_window():
    from methane.qualification_analysis import recovery_windows

    r = record()
    r["config"].update(
        sensors={"probe_fraction": 0.1, "confirmation_hours": 2},
        recovery_policy={"version": "scheduled-load-tests/4"},
    )
    r["config"]["plant"]["min_load_fraction"] = 0.3
    r["timeline"][0]["recovery"] = {
        "deadline_openings": [
            {
                "opened_at": 20,
                "available_boundary": 20,
                "due_hour": 24,
                "hard_deadline": 44,
                "capacity_estimate_kw": 218.4,
            }
        ]
    }
    v = recovery_windows(r)[0]
    assert v["required_increases"] == 6
    assert v["optimistic_minimum_intervals"] == 11
    assert v["available_intervals"] == 4
    assert v["shorter_than_test_count"]
    # A longer window satisfies only this necessary count, not feasibility.
    r["timeline"][0]["recovery"]["deadline_openings"][0]["due_hour"] = 44
    assert not recovery_windows(r)[0]["shorter_than_test_count"]


def test_missing_numerical_repeat_does_not_report_zero_spread():
    a = record()
    b = copy.deepcopy(a)
    b["label"]["repetition"] = 2
    b["summary"] = None
    b["hours"] = 1
    result = numerical_spreads([a, b])[0]
    assert result["completed"] == 1 and result["declared"] == 2
    assert result["exact_physical_trace_identity"] is None
    assert result["spreads"]["methane_kg"] is None
