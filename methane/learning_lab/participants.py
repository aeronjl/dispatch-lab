"""Real participant responses are separate from scripted software checks."""

from datetime import UTC, datetime

QUESTIONS = {
    "mechanism": "Explain how an observed condition affects a proposed operating decision.",
    "assumption": "Find one assumed measurement channel and explain what it cannot establish.",
    "trace": "Trace a policy prediction to its inputs, dataset and original source version.",
    "unconfirmed": "Find an unconfirmed or failed intervention; explain whether recovery is known.",
    "evidence": "Explain whether a held-out synthetic comparison establishes field performance.",
    "return": "Return to the same component, controller and hour in the simulation.",
}


def record(store, *, participant, facilitator, responses, issues, basis="participant-session"):
    if basis not in ("participant-session", "agent-rehearsal"):
        raise ValueError("Identify a real participant session or an agent rehearsal")
    if not participant.strip() or not facilitator.strip() or set(responses) != set(QUESTIONS):
        raise ValueError("Use a participant pseudonym, facilitator and all six response fields")
    for value in responses.values():
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Record the participant's words or explicitly record no answer")
    for issue in issues:
        if (
            set(issue) != {"question", "misunderstanding", "severity", "resolution"}
            or issue["question"] not in QUESTIONS
            or issue["severity"] not in ("minor", "material")
        ):
            raise ValueError(
                "Identify each misunderstanding, severity and resolution (blank if open)"
            )
    value = dict(
        version="comprehension-session/1",
        participant=participant,
        facilitator=facilitator,
        basis=basis,
        recorded_at=datetime.now(UTC).isoformat(),
        questions=QUESTIONS,
        responses=responses,
        issues=issues,
        status="material confusion unresolved"
        if any(i["severity"] == "material" and not i["resolution"].strip() for i in issues)
        else "recorded; facilitator review required",
        scope="Participant words and facilitator interpretation; not an automated test result or proof of general usability",
    )
    return dict(id=store.put("walkthrough", value), **value)
