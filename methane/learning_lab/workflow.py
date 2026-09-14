"""Study integration, immutable model selection and explicit comparison recipes."""

from dataclasses import replace

from methane.policy import Policy


def deployed_policy(store, config, controller, deployment_id, policy=None):
    from methane.simulation import STRATEGIES

    objective = STRATEGIES[controller]
    if policy is None:
        recovery = config.recovery_policy
        if (
            objective == "greedy"
            and recovery is not None
            and recovery.version != "scheduled-load-tests/1"
        ):
            recovery = replace(recovery, version="scheduled-load-tests/1")
        policy = Policy(
            objective=objective,
            version="dispatch-lab/policy/5",
            recovery=recovery,
            service=config.service_policy if objective != "greedy" else None,
            investigation=config.investigation_policy if objective != "greedy" else None,
        ).to_dict()
    return Policy(
        **{
            **policy,
            "version": "dispatch-lab/policy/5",
            "deployment": store.get("deployment", deployment_id),
        }
    ).to_dict()


def comparison_template(
    store,
    design_id,
    environment_id,
    deployment_ids,
    *,
    name="Policy and reserve comparison",
    seed=7,
):
    from methane.siting import production, workflow

    if len(deployment_ids) > 12:
        raise ValueError("At most 12 declared experimental policies per template")
    cases = [
        dict(
            design_id=design_id,
            environment_id=environment_id,
            controller=controller,
            seed=seed,
            label="Reference / " + controller,
        )
        for controller in ("Greedy", "MPC · methane", "MPC · economics")
    ]
    for key in deployment_ids:
        d = store.get("deployment", key)
        for controller in ("MPC · methane", "MPC · economics"):
            cases.append(
                dict(
                    design_id=design_id,
                    environment_id=environment_id,
                    controller=controller,
                    seed=seed,
                    deployment_id=key,
                    label=d["name"] + " / " + controller,
                )
            )
    study = production.create(
        store,
        name=name,
        cases=cases,
        purpose="Compare matched starting information and physical exposure; report production, controllable cost, inventory, fallback and unresolved obligations without requiring learning to win",
    )
    recipe = workflow.save_template(
        store,
        study["id"],
        name=name,
        method="Same design, environment and seed. Reference Greedy and both MPC objectives; matched experimental policies. Inspect source identity, reserve preference penalty separately from actual decision costs, diagnosis, service outcomes and ending inventories. Repeat with held-out weather/configurations, adverse forecasts, expensive interventions and support-loss scenarios before any general conclusion.",
        limitations="A ready-to-run template, not a scientific finding. No fixed ownership incentive, inventory sale credit or supported field-autonomy claim. Service maintenance rules are frozen in the selected design; changing them is a separate design comparison.",
    )
    return dict(study_id=study["id"], template=recipe)


def index(store):
    return dict(
        datasets=[
            {k: v[k] for k in ("id", "name", "sample_count", "scope")}
            for v in store.list("dataset")
        ],
        models=[
            {k: v.get(k) for k in ("id", "name", "task", "units", "dataset_id")}
            for v in store.list("model")
        ],
        deployments=[
            {k: v.get(k) for k in ("id", "name", "mode", "model_id")}
            for v in store.list("deployment")
        ],
        evaluations=[
            {k: v.get(k) for k in ("id", "name", "status", "comparisons", "reason")}
            for v in store.list("evaluation")
        ],
        tasks=[
            dict(id=k, name=v[0], unit=v[1])
            for k, v in __import__(
                "methane.learning_lab.estimators", fromlist=["TASKS"]
            ).TASKS.items()
        ],
    )
