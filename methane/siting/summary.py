"""Read each saved partition once for whole-case reporting.

The full recording remains authoritative. Only the established cost port and
descriptive outcome operands enter the in-memory report view; historical service
decision trees do not need to be decoded again for every scalar sum.
"""

from methane.services.pricing import projected_row


def report_row(row, *, finite_service_prices, final=False):
    value = dict(row)
    field = row.get("field_operations")
    if finite_service_prices and field is not None:
        compact = projected_row(row)["field_operations"]
        # Additional operands used by services.outcomes and simulation.summarise.
        for key in (
            "version",
            "treated_area_m2",
            "cleanings_completed",
            "water_used_l",
            "standby",
            "soiling_loss_kw",
        ):
            if key in field:
                compact[key] = field[key]
        compact["decision"] = {"inspection": field.get("decision", {}).get("inspection")}
        if final:
            # The user's terminal-work view retains the complete final state.
            compact["state"] = field["state"]
        value["field_operations"] = compact
    return value


def calculate(store, study_id, case, progress=None, cancelled=None):
    from methane.cancellation import CancelledOperation
    from methane.config import Config
    from methane.simulation import summarise
    from methane.siting.production import calendar, entries, products, read_blob

    items = entries(store, study_id, case["case_id"])
    config = Config.from_dict(case["config"])
    rows, truth = [], []
    for item in items:
        if cancelled and cancelled():
            raise CancelledOperation()
        if item["start_hour"] != len(rows):
            raise ValueError("Missing or overlapping report intervals")
        part = read_blob(store, item.get("summary_sha256", item["period_sha256"]))
        part = part.get("value", part)
        for row in part["records"][case["controller"]]:
            if row["hour"] != len(rows):
                raise ValueError("Missing or duplicated report hour")
            rows.append(
                report_row(
                    row,
                    finite_service_prices=config.service_economics is not None,
                    final=row["hour"] == case["hours"] - 1,
                )
            )
        truth.extend(
            {k: t[k] for k in ("hour", "capacity_kw", "injected_fault_active")}
            for t in part["retrospective_truth_by_controller"][case["controller"]]
        )
        if len(rows) != item["next_hour"] or len(truth) != len(rows):
            raise ValueError("Report partition does not match its committed interval count")
        if progress:
            progress(len(rows), case["hours"])
    if len(rows) != case["hours"] or len(truth) != len(rows):
        raise ValueError("Whole-case report requires every declared interval")
    summary = summarise(rows, config, truth)
    summary.update(
        products=products(rows),
        calendar=calendar(rows),
        scope="Entire continuous case; allocation evaluated once, not added from partition allowances",
    )
    return summary
