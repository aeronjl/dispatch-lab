"""Numerical editions preserve inputs and report scoped differences explicitly."""

from methane.siting.store import digest


def repeat(store, study_id):
    from methane.siting import production, workflow

    original = store.get("study", study_id)
    recipe = workflow.recipe(original)
    recipe["name"] += " / numerical edition"
    for case, before in zip(recipe["cases"], original["cases"], strict=True):
        case["repetition"] = before["repetition"] + 1
    return production.create(
        store, **recipe, search=dict(kind="numerical-edition/1", original_study_id=study_id)
    )


def compare(store, original_id, edition_id):
    from methane.siting.production import entries, read_blob

    studies = [store.get("study", key) for key in (original_id, edition_id)]
    if len(studies[0]["cases"]) != len(studies[1]["cases"]):
        raise ValueError("Numerical editions need the same case count")
    fields = (
        "state",
        "requested",
        "applied",
        "observations_after",
        "diagnosis_after",
        "forced_trip",
        "reactor_start",
        "electrolyser_start",
    )
    differences, missing, case_inputs = [], [], []

    def recorded(study_id, case):
        values = {}
        for entry in entries(store, study_id, case["case_id"]):
            part = read_blob(store, entry["period_sha256"])["value"]
            for row in part["records"][case["controller"]]:
                values[row["hour"]] = {k: row.get(k) for k in fields}
                if len(values) > 100000:
                    raise ValueError("Difference inspection budget is 100,000 recorded hours")
        return values

    def changes(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(a.keys() | b.keys()):
                yield from changes(a.get(key), b.get(key), path + "." + key)
        elif a != b:
            yield dict(
                path=path,
                original=a,
                edition=b,
                absolute_difference=abs(a - b)
                if type(a) in (float, int) and type(b) in (float, int)
                else None,
            )

    for a, b in zip(studies[0]["cases"], studies[1]["cases"], strict=True):
        identity_fields = (
            "config",
            "utilities",
            "environment_id",
            "controller",
            "policy",
            "uncertainty",
            "hours",
        )
        input_changes = list(
            changes(
                {k: a.get(k) for k in identity_fields},
                {k: b.get(k) for k in identity_fields},
                "inputs",
            )
        )
        case_inputs.append(dict(case_id=a["case_id"], input_differences=input_changes))
        x, y = recorded(original_id, a), recorded(edition_id, b)
        for hour in range(max(a["hours"], b["hours"])):
            if hour not in x or hour not in y:
                missing.append(
                    dict(
                        case_id=a["case_id"],
                        hour=hour,
                        original_recorded=hour in x,
                        edition_recorded=hour in y,
                    )
                )
            else:
                differences.extend(
                    dict(case_id=a["case_id"], hour=hour, **d)
                    for d in changes(x[hour], y[hour], "record")
                )
    value = dict(
        version="numerical-edition-differences/1",
        title="Numerical edition differences",
        study_ids=[original_id, edition_id],
        sources=[s["source"]["content_hash"] for s in studies],
        status="incomplete"
        if missing
        else "different"
        if differences or any(c["input_differences"] for c in case_inputs)
        else "matched within comparison scope",
        input_comparison=case_inputs,
        differences=differences,
        missing_hours=missing,
        compared_fields=list(fields),
        comparison="Exact recorded operands; no tolerance hides differences. Timing, solver search logs, presentation and detailed audit operands are excluded. Original recordings remain available for those fields.",
        scope="Numerical consistency is not field validation. Different physical inputs make this a changed-assumption edition, not a solver repeat.",
    )
    value["content_id"] = digest(value)
    return dict(id=store.put("difference", value), **value)
