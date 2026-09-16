"""Small Sites-facing transport for the learning workspace."""

import json


def perform(store, operation, key, data):
    from methane.learning_lab import datasets, deployment, jobs, participants, workflow

    if operation == "lab-index":
        return {
            **workflow.index(store),
            "budget": jobs.BUDGET,
            "jobs": [
                {"id": j["id"], "operation": j["operation"], **jobs.poll(store, j["id"])}
                for j in store.list("training")[-20:]
                if (store.root / "learning-jobs" / j["id"] / "state.json").exists()
            ],
        }
    if operation == "lab-episodes":
        from methane.siting.production import inspect

        episodes = []
        for study in store.list("study"):
            for case in inspect(store, study["id"])["cases"]:
                env = store.get("environment", case["environment_id"])
                episodes.append(
                    dict(
                        study_id=study["id"],
                        case_id=case["case_id"],
                        name=study["name"] + " / " + case["label"],
                        controller=case["controller"],
                        start=env["start"],
                        end=env["end"],
                        complete=case["completed_hours"] == case["hours"],
                    )
                )
        return dict(episodes=episodes)
    if operation == "lab-start":
        if data.get("operation") == "requirements":
            raise ValueError("Use requirements-assess to freeze original study inputs")
        return jobs.launch(store, **data)
    if operation == "lab-job":
        return jobs.poll(store, key, data.get("cancel", False))
    if operation == "lab-register":
        return deployment.register(store, **data)
    if operation == "lab-template":
        return workflow.comparison_template(store, **data)
    if operation == "lab-differences":
        from methane.learning_lab.editions import compare

        return compare(store, **data)
    if operation == "lab-reconstruct":
        return datasets.reconstruct(store, key)
    if operation == "lab-session":
        return participants.record(store, **data)
    if operation == "lab-questions":
        return dict(questions=participants.QUESTIONS, sessions=store.list("walkthrough"))
    if operation == "lab-get":
        kind = data["kind"]
        if kind not in ("dataset", "model", "deployment", "evaluation", "training", "walkthrough"):
            raise ValueError("Unknown learning record type")
        value = store.get(kind, key)
        if kind == "dataset":
            samples = json.loads(store.read_raw(value["observations_sha256"]))
            value["observation_preview"] = samples[:3]
            value["label_boundary"] = (
                "Retrospective labels are separate; no label data is returned to this observation view"
            )
        if kind == "evaluation":
            value["preview_scope"] = (
                "First 24 held-out predictions per strategy. Publication contains the complete immutable record."
            )
            value["outcomes"] = {k: v[:24] for k, v in value.get("outcomes", {}).items()}
            value["exclusions"] = value["exclusions"][:24]
        return dict(id=key, **value)
    raise ValueError("Unknown learning operation")
