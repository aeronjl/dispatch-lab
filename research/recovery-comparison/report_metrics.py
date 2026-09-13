"""Dated report derivations from saved v3 episode records; no simulation imports."""

from collections import Counter

VERSION = "recovery-report-episodes/1"


def episode_metrics(history):
    """Count each receipt-defined window once, using its latest recorded outcome.

    The legacy recovery_deadline_misses column counts a different scheduler
    status. It is deliberately neither read nor rewritten here. Escalation can
    precede any completed mission, so its interval count is not a window count.
    """
    episodes = {}
    for row in history:
        loop = row.get("loop") or {}
        if loop.get("version") != "post-mission-verification-episodes/1":
            raise ValueError("Unknown or missing original verification episode schema")
        for item in loop["episodes"]:
            key = tuple(item["receipt_ids"])
            if not key:
                raise ValueError("A verification window needs original receipt identities")
            if key in episodes:
                for field in ("opened_at", "available_boundary", "due_hour"):
                    if item[field] != episodes[key][field]:
                        raise ValueError("A saved verification boundary changed")
                for field in ("closed_at", "outcome"):
                    if field in episodes[key] and item.get(field) != episodes[key][field]:
                        raise ValueError("A saved closed window was reinterpreted")
            episodes[key] = item
    outcomes = Counter(x.get("outcome", "open at ending boundary") for x in episodes.values())
    return dict(
        version=VERSION,
        applicable=bool(history),
        windows_opened=len(episodes),
        expired_windows=outcomes["verification deadline missed"],
        observer_confirmed_windows=outcomes["observer confirmed"],
        original_deadline_already_missed_windows=sum(
            bool(x.get("original_deadline_missed")) for x in episodes.values()
        ),
        escalation_intervals=sum(x["status"] == "escalation-required" for x in history),
        outcomes=dict(outcomes),
        scope="Derived from original episode snapshots. Distinct completed-mission windows and escalation intervals are separate. This does not rewrite the legacy recovery_deadline_misses metric.",
    )
