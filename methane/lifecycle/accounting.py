"""Cash, consumption and allocation remain separate; stock is not an instant expense."""


def ledger(rows):
    entries = [r for r in rows if r.get("lifecycle")]
    if not entries:
        return None
    cash, construction, maintenance = {}, 0.0, 0.0
    parts = {}
    crew = 0.0
    for row in entries:
        r = row["lifecycle"]
        for k, v in r["expenditure"].items():
            cash[k] = cash.get(k, 0) + v
        crew += r["decision"]["crew_hours"]
        direct = sum(
            r["expenditure"][k]
            for k in ("crew_eur", "callout_eur", "equipment_eur", "external_energy_eur")
        )
        if r["accounting"]["work_kind"] == "construction":
            # Purchases may occur alongside construction; preserve their stock classification.
            material = r["expenditure"]["materials_eur"] - sum(
                p["eur"] for p in r["decision"]["purchases"]
            )
            construction += direct + material
        else:
            maintenance += direct
        consumed = r["consumption"]
        if consumed:
            parts[consumed["asset"]] = parts.get(consumed["asset"], 0) + consumed["part_value_eur"]
    end = entries[-1]["lifecycle"]["after"]
    return dict(
        version="lifecycle-accounting/1",
        hours=len(entries),
        expenditure=cash,
        cash_eur=sum(v for k, v in cash.items() if k.endswith("_eur")),
        construction_capital_eur=construction,
        maintenance_resource_eur=maintenance,
        consumed_parts_eur=parts,
        project_crew_hours=crew,
        accepted_capacity=end["availability"],
        packages=end["packages"],
        ending_condition=end["condition"],
        unresolved_jobs=[j for j in end["jobs"] if j["status"] != "verified"],
        verified_replacements=sum(j["status"] == "verified" for j in end["jobs"]),
        scope="Cash includes purchased opening and replenishment stock. Allocated replacement uses the larger of the existing wear/calendar allowance and parts consumed, never their sum. Work-package capital replaces the declared share of the original installation allowance. Additional project labour is distinct from the field-service crew. Ending stock has no assumed sale proceeds.",
    )


def allocation_adjustments(p, c, cap, rows, allowances):
    value = ledger(rows)
    if value is None:
        return {}, None
    selected = [r["lifecycle"]["accounting"] for r in rows if r.get("lifecycle")]
    before, after = selected[0]["before"], selected[-1]["after"]
    adjustments = {"project_service": after["maintenance_eur"] - before["maintenance_eur"]}
    assets = selected[0]["condition_assets"]

    def pool(state, asset):
        calendar = (
            cap["solar"] / c.solar_years * state["hours"] / 8760
            if asset == "solar"
            else cap["electrolyser"]
            * c.stack_share
            / c.stack_calendar_years
            * state["hours"]
            / 8760
        )
        usage = (
            0
            if asset == "solar"
            else cap["electrolyser"]
            * c.stack_share
            / c.stack_operating_hours
            * (
                state["electrolyser_hours"]
                + state["electrolyser_starts"] * c.start_equivalent_hours
            )
        )
        return max(calendar, usage, state["consumed_parts"].get(asset, 0))

    for asset, allowance in (
        ("solar", cap["solar"] / c.solar_years * len(rows) / 8760),
        ("electrolyser", allowances["stack"][2]),
    ):
        if asset in assets:
            adjustments[asset] = pool(after, asset) - pool(before, asset) - allowance
    fractions = selected[0]["construction_fractions"]
    replaced_base = (
        sum(
            fractions[a] * capital
            for a, capital in (
                ("solar", cap["solar"]),
                ("battery", cap["battery_cells"] + cap["battery_power"]),
                ("electrolyser", cap["electrolyser"]),
                ("reactor", cap["reactor"]),
            )
        )
        * c.installation_fraction
    )
    adjustments["site"] = (
        (
            after["construction_eur_hours"]
            - before["construction_eur_hours"]
            - replaced_base * len(rows)
        )
        / c.other_equipment_years
        / 8760
    )
    value["allocation_adjustments"] = adjustments
    value["replaced_installation_basis_eur"] = replaced_base
    value["allocation_boundary"] = dict(before=before, after=after)
    return adjustments, value


def decision_adjustment(p, c, rows):
    selected = [r["lifecycle"]["accounting"] for r in rows if r.get("lifecycle")]
    if not selected:
        return 0
    a, b = selected[0]["before"], selected[-1]["after"]
    rate = p.electrolyser_kw * c.electrolyser_eur_per_kw * c.stack_share / c.stack_operating_hours

    def usage(state):
        return rate * (
            state["electrolyser_hours"] + state["electrolyser_starts"] * c.start_equivalent_hours
        )

    def value(state):
        return (
            state["maintenance_eur"]
            + state["consumed_parts"].get("solar", 0)
            + max(usage(state), state["consumed_parts"].get("electrolyser", 0))
        )

    return value(b) - value(a) - (usage(b) - usage(a))
