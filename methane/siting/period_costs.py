"""A recorded window consumes the original accumulated service allowance pool."""

import copy

from methane.service_economics import field_costs
from methane.services.pricing import projected_row


def difference(after, before):
    return None if after is None or before is None else after - before


def services(rows, assumptions, prefix, detailed=False):
    before = field_costs(prefix, assumptions)
    after = field_costs([*prefix, *(projected_row(r) for r in rows)], assumptions)
    result = copy.deepcopy(after)
    for key in ("total_eur", "variable_and_wear_eur"):
        result[key] = difference(after[key], before[key])
    result["components"] = {
        k: difference(v, before["components"].get(k, 0)) for k, v in after["components"].items()
    }
    for view, v in result["views"].items():
        b = before["views"][view]
        for key in ("total_eur", "known_subtotal_eur"):
            if key in v:
                v[key] = difference(v[key], b[key])
        v["components"] = {
            k: difference(value, b["components"].get(k, 0)) for k, value in v["components"].items()
        }
    result["quantities"] = {
        k: difference(v, before["quantities"].get(k, 0)) for k, v in after["quantities"].items()
    }
    result["period_difference"] = dict(
        prefix_hours=len(prefix),
        period_hours=len(rows),
        components={
            k: dict(before=before["components"].get(k, 0), after=v)
            for k, v in after["components"].items()
        },
        method="Cumulative allocation after window minus cumulative allocation before; original wear/parts pool retained. Closing stocks are not differences.",
    )
    result["boundaries"].append(result["period_difference"]["method"])
    return result
