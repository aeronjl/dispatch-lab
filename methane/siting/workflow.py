"""Reusable experiment recipes and explicitly scoped computation estimates."""

import math

from methane.siting.store import digest

REPORT_SECTIONS = ("question", "method", "findings", "limitations", "next_questions")


def recipe(manifest):
    """Reuse inputs, never outputs, checkpoints or a prior source qualification."""
    return dict(
        name=manifest["name"],
        mode=manifest["mode"],
        purpose=manifest["purpose"],
        partition_hours=manifest["partition_hours"],
        cases=[
            dict(
                **{
                    k: c[k]
                    for k in (
                        "design_id",
                        "environment_id",
                        "controller",
                        "role",
                        "label",
                        "policy",
                        "uncertainty",
                    )
                    if k in c
                },
                seed=c["config"]["scenario"]["seed"],
                repetition=1,
            )
            for c in manifest["cases"]
        ],
    )


def save_template(store, study_id, *, name, method, limitations, question=None):
    manifest = store.get("study", study_id)
    if not all(isinstance(v, str) and v.strip() for v in (name, method, limitations)):
        raise ValueError("A template needs a name, comparison method and limitations")
    value = dict(
        schema_version="site-experiment-template/1",
        name=name,
        question=question or manifest["purpose"],
        method=method,
        limitations=limitations,
        original_study_id=study_id,
        original_source=manifest["source"],
        recipe=recipe(manifest),
        writeup={
            "question": question or manifest["purpose"],
            "method": method,
            "findings": "",
            "limitations": limitations,
            "next_questions": "",
        },
        boundary="A reusable recipe, not a completed result. New editions use the current application; saved designs and weather retain their original identities.",
    )
    key = store.put("template", value)
    return dict(id=key, **value)


def runtime_estimate(value, seconds_per_hour=None):
    """Partition wall time includes numerical execution and saved-period I/O.

    Never borrow timing from another source/design/controller. A supplied pilot
    rate is an explicit user assumption. The range is a workload allowance, not
    a probability interval or a solver completion guarantee.
    """
    if seconds_per_hour is not None:
        if not math.isfinite(seconds_per_hour) or seconds_per_hour <= 0:
            raise ValueError("Pilot seconds per simulated hour must be finite and positive")
    samples = {}

    def signature(case):
        return digest({k: case.get(k) for k in ("config", "controller", "policy")})

    for case in value["cases"]:
        sample = samples.setdefault(signature(case), [0.0, 0])
        for period in case["periods"]:
            seconds = period.get("elapsed_seconds")
            count = period["next_hour"] - period["start_hour"]
            if seconds is not None and math.isfinite(seconds) and seconds > 0 and count > 0:
                sample[0] += seconds
                sample[1] += count
    estimate = 0.0
    unknown = 0
    remaining = 0
    for case in value["cases"]:
        hours = case["hours"] - case["completed_hours"]
        remaining += hours
        seconds, count = samples[signature(case)]
        rate = (
            seconds_per_hour if seconds_per_hour is not None else seconds / count if count else None
        )
        if rate is None:
            unknown += hours
        else:
            estimate += rate * hours
    return dict(
        status="unavailable" if unknown else "estimated" if remaining else "complete",
        remaining_hours=remaining,
        unestimated_hours=unknown,
        seconds=estimate if not unknown else None,
        range_seconds=[estimate * 0.5, estimate * 2] if not unknown else None,
        basis="Supplied pilot assumption"
        if seconds_per_hour is not None
        else "Saved partition timings for this source, configuration and controller",
        scope="0.5–2× workload allowance, not a confidence interval. Excludes queue wait, final reconciliation and exports; contention and solver behaviour can change runtime. Older recordings have no timing estimate. Supply a measured pilot rate before starting, or wait for a matching partition.",
    )
