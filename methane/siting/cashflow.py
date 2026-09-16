"""Dated project cash flows over recorded production, separate from wear allocation."""

import calendar
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from methane.config import Config
from methane.costing import capital, water_rate
from methane.siting.contracts import Record
from methane.siting.production import PeriodRows, entries, inspect
from methane.siting.store import digest


class CashItem(Record):
    name: str = Field(min_length=1, max_length=200)
    category: Literal["initial", "annual", "replacement", "decommissioning", "residual"]
    eur: float | None = Field(default=None, ge=0)
    year: int = Field(default=0, ge=0, le=40)
    evidence_id: str | None = None
    assumption: str = Field(min_length=1, max_length=2000)


class CashScenario(Record):
    schema_version: Literal["site-cash-scenario/1"] = "site-cash-scenario/1"
    name: str = "Illustrative pre-tax unlevered project"
    life_years: int = Field(default=20, ge=1, le=40)
    price_year: int = Field(default=2026, ge=2000, le=2100)
    quote_date: date = date(2026, 9, 13)
    valid_until: date | None = None
    currency: Literal["EUR"] = "EUR"
    discount_rate: float = Field(default=0.07, gt=-1, le=1)
    price_basis: Literal["real", "nominal"] = "real"
    inflation: float = Field(default=0, gt=-1, le=0.5)
    methane_eur_per_kg: float | None = Field(default=1, ge=0)
    methane_acceptance_fraction: float = Field(default=0, ge=0, le=1)
    offtake_kgph: float | None = Field(default=None, ge=0)
    co2_eur_per_kg: float | None = Field(default=0.15, ge=0)
    co2_payment_basis: Literal["delivered", "consumed"] = "delivered"
    water_eur_per_m3: float | None = Field(default=None, ge=0)
    repeat_partial_period: bool = False
    items: list[CashItem] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=lambda: [
            "An offtake acceptance scenario, not gas certification",
            "Repeat observed climate years cyclically; lifetime production ageing is not inferred",
            "No hydrogen revenue, CO2 capture credit, subsidy, tax or financing",
        ]
    )

    @model_validator(mode="after")
    def consistent(self):
        if self.price_basis == "real" and self.inflation != 0:
            raise ValueError(
                "Real cash flows require zero inflation; supply a consistent nominal discount rate for nominal flows"
            )
        if self.valid_until and self.valid_until < self.quote_date:
            raise ValueError("Quote validity precedes its date")
        if any(i.year > self.life_years for i in self.items):
            raise ValueError("Cash event lies outside the project horizon")
        return self


def defaults(config):
    c = Config.from_dict(config)
    cap = capital(c.plant, c.costs)
    from methane.integration import settings

    integration = settings(c.plant)
    if integration and (
        integration.installed_eur is None or integration.fixed_eur_per_year is None
    ):
        raise ValueError(
            "Price additional plant interfaces in Equipment & evidence before creating a cash scenario"
        )
    construction_basis = 0
    if c.lifecycle:
        fractions = {
            a: sum(x["fraction"] for x in c.lifecycle["packages"] if x["asset"] == a)
            for a in ("solar", "battery", "electrolyser", "reactor")
        }
        construction_basis = (
            sum(
                fractions[a] * v
                for a, v in (
                    ("solar", cap["solar"]),
                    ("battery", cap["battery_cells"] + cap["battery_power"]),
                    ("electrolyser", cap["electrolyser"]),
                    ("reactor", cap["reactor"]),
                )
            )
            * c.costs.installation_fraction
        )
    items = [
        CashItem(
            name=k,
            category="initial",
            eur=v,
            assumption="Existing illustrative capital scaling; no vendor quotation",
        )
        for k, v in cap.items()
    ]
    items += [
        CashItem(
            name="Installation and site setup",
            category="initial",
            eur=sum(cap.values()) * c.costs.installation_fraction
            + c.costs.site_setup_eur
            - construction_basis,
            assumption="Existing illustrative installation/setup, minus the work-package asset share booked through recorded lifecycle invoices"
            if c.lifecycle
            else "Existing illustrative installation/setup assumption",
        ),
        CashItem(
            name="Initial CO2 stock",
            category="initial",
            eur=c.plant.initial_co2_kg * c.costs.co2_eur_per_kg,
            assumption="Purchased opening stock; not charged again as a new delivery",
        ),
        CashItem(
            name="Standing plant operation",
            category="annual",
            eur=c.costs.fixed_opex_eur_per_year,
            assumption="Existing fixed operating cost",
        ),
    ]
    if integration:
        items.extend(
            [
                CashItem(
                    name="Additional installed plant interfaces",
                    category="initial",
                    eur=integration.installed_eur,
                    assumption="User-entered additional installed cost; excludes existing assets and installation allowance",
                ),
                CashItem(
                    name="Additional interface maintenance",
                    category="annual",
                    eur=integration.fixed_eur_per_year,
                    assumption="User-entered standing maintenance; no duplicate wear allowance",
                ),
            ]
        )
    for name, kind in (
        ("Land rights or lease", "annual"),
        ("Surveys and permitting", "initial"),
        ("CO2 treatment and delivery logistics", "annual"),
        ("Product handling and export", "annual"),
        ("Insurance", "annual"),
        ("Decommissioning", "decommissioning"),
    ):
        items.append(
            CashItem(
                name=name,
                category=kind,
                assumption="Unquoted; enter a dated amount or an explicit zero-cost boundary",
            )
        )
    if c.field_operations.enabled:
        items.append(
            CashItem(
                name="Service fleet, depot and opening spares",
                category="initial",
                assumption="Site service procurement quotation required; not inferred from ownership allowance",
            )
        )
        if c.service_economics is None:
            items.append(
                CashItem(
                    name="Service consumables and interventions",
                    category="annual",
                    assumption="Supply a service cash budget; legacy wear allocation is not a cash invoice",
                )
            )
    for name, value, interval in (
        ("Battery cells", cap["battery_cells"], c.costs.battery_calendar_years),
        (
            "Electrolyser stack",
            cap["electrolyser"] * c.costs.stack_share,
            c.costs.stack_calendar_years,
        ),
    ):
        if (
            c.lifecycle
            and name == "Electrolyser stack"
            and any(s["asset"] == "electrolyser" for s in c.lifecycle["conditions"])
        ):
            continue  # Recorded purchases replace this hypothetical calendar schedule.
        year = int(interval)
        while year > 0 and year < 20:
            items.append(
                CashItem(
                    name=name + " replacement",
                    category="replacement",
                    eur=value,
                    year=year,
                    assumption="Illustrative calendar replacement cash schedule; usage wear is excluded from this ledger",
                )
            )
            year += int(interval)
    return CashScenario(
        methane_eur_per_kg=c.costs.methane_eur_per_kg,
        co2_eur_per_kg=c.costs.co2_eur_per_kg,
        water_eur_per_m3=c.costs.water_eur_per_m3,
        items=items,
    ).model_dump(mode="json")


def payback(cumulative):
    crossings = [
        i for i in range(1, len(cumulative)) if cumulative[i] >= 0 and cumulative[i - 1] < 0
    ]
    sustained = next(
        (
            i
            for i in range(1, len(cumulative))
            if cumulative[i] >= 0 and all(v >= 0 for v in cumulative[i:])
        ),
        None,
    )
    return dict(
        first_crossing_year=crossings[0] if crossings else (0 if cumulative[0] >= 0 else None),
        sustained_recovery_year=sustained,
        reversals=[i for i in range(1, len(cumulative)) if cumulative[i] < 0 <= cumulative[i - 1]],
        scope="Year-end cash boundaries; no within-year interpolation",
    )


def calculate(initial, years, discount_rate):
    """Independent arithmetic port; amounts are signed net cash and positive accepted kg."""
    if not -1 < discount_rate <= 1 or initial < 0:
        raise ValueError("Invalid initial capital or discount rate")
    simple, discounted = [-initial], [-initial]
    present_cost, present_output = initial, 0.0
    ledger = []
    for i, row in enumerate(years, 1):
        factor = (1 + discount_rate) ** i
        cash = row["receipts_eur"] - row["cost_eur"]
        simple.append(simple[-1] + cash)
        discounted.append(discounted[-1] + cash / factor)
        present_cost += row["cost_eur"] / factor
        present_output += row["accepted_kg"] / factor
        ledger.append(
            {
                **row,
                "year": i,
                "discount_factor": factor,
                "net_cash_eur": cash,
                "discounted_net_eur": cash / factor,
                "cumulative_eur": simple[-1],
                "discounted_cumulative_eur": discounted[-1],
            }
        )
    return dict(
        npv_eur=discounted[-1],
        levelised_eur_per_kg=present_cost / present_output if present_output > 0 else None,
        discounted_cost_eur=present_cost,
        discounted_accepted_kg=present_output,
        simple_payback=payback(simple),
        discounted_payback=payback(discounted),
        ledger=ledger,
    )


def report(store, study_id, case_id, assumptions):
    scenario = CashScenario(**assumptions)
    study = inspect(store, study_id)
    case = next((c for c in study["cases"] if c["case_id"] == case_id), None)
    if case is None or case["summary"] is None or case["completed_hours"] != case["hours"]:
        raise ValueError("Cash-flow projection needs a fully executed declared case")
    config = Config.from_dict(case["config"])
    design = store.get("design", case["design_id"])
    site = store.get("site", design["site_revision"])
    evidence_ids = set(scenario.evidence_ids) | {
        i.evidence_id for i in scenario.items if i.evidence_id
    }
    expired = []
    for key in evidence_ids:
        e = store.get("evidence", key)
        if e["site_id"] != site["site_id"]:
            raise ValueError("Quotation evidence belongs to another site")
        if e.get("valid_until") and e["valid_until"][:10] < scenario.quote_date.isoformat():
            expired.append(key)
    rows = PeriodRows(store, entries(store, study_id, case_id), case["controller"])
    observed = {}
    for r in rows:
        year = int(r["time"][:4])
        a = observed.setdefault(
            year,
            dict(
                hours=0,
                gross_kg=0,
                accepted_kg=0,
                co2_kg=0,
                water_m3=0,
                consumables_eur=0,
                lifecycle_cash_eur=0,
                lifecycle_opening_eur=0,
            ),
        )
        a["hours"] += 1
        if r.get("lifecycle"):
            expense = r["lifecycle"]["expenditure"]
            a["lifecycle_opening_eur"] += expense["opening_stock_eur"]
            a["lifecycle_cash_eur"] += sum(
                v for k, v in expense.items() if k.endswith("_eur") and k != "opening_stock_eur"
            )
        gross = r["applied"]["methane_kg"]
        a["gross_kg"] += gross
        a["accepted_kg"] += min(
            gross * scenario.methane_acceptance_fraction,
            scenario.offtake_kgph if scenario.offtake_kgph is not None else float("inf"),
        )
        a["co2_kg"] += (
            r["co2_delivered_kg"] + r["co2_rejected_kg"]
            if scenario.co2_payment_basis == "delivered"
            else r["co2_consumed_kg"]
        )
        a["water_m3"] += r["h2_produced_kg"] * water_rate(config.plant, config.costs) / 1000
        a["consumables_eur"] += r["h2_produced_kg"] * config.costs.consumables_eur_per_kg
        if r.get(
            "intervention_accounting", "legacy-alarm-allowance/1"
        ) == "legacy-alarm-allowance/1" and r.get("incident"):
            a["consumables_eur"] += (
                config.costs.repair_eur_per_incident + config.costs.visit_eur_per_incident
            )
    partial = [
        y for y, v in observed.items() if v["hours"] != (8784 if calendar.isleap(y) else 8760)
    ]
    if config.lifecycle and (partial or scenario.life_years > len(observed)):
        raise ValueError(
            "Lifecycle cash projection requires a continuous recorded path covering every complete project year. Ageing, commissioning and replacement cannot be extrapolated by repeating a partial period or an earlier lifecycle year. Use the dated period expenditure report or simulate the requested chronology."
        )
    if partial and not scenario.repeat_partial_period:
        raise ValueError(
            "A partial calendar year cannot silently become annual yield. Run full years or explicitly enable a partial-period extrapolation scenario."
        )
    missing = [i.name for i in scenario.items if i.eur is None]
    for field in ("methane_eur_per_kg", "co2_eur_per_kg", "water_eur_per_m3"):
        if getattr(scenario, field) is None:
            missing.append(field)
    service_cash = 0
    service_by_year = {}
    if config.service_economics:
        from methane.service_economics import report as service_report

        service = service_report(rows, config.service_economics)
        expense = service["views"]["expenditure"]
        if expense["total_eur"] is None:
            missing += list(expense["unpriced"])
        else:
            if config.service_economics.get(
                "initial_asset_purchase"
            ) or config.service_economics.get("initial_stock_purchase"):
                raise ValueError(
                    "Opening service procurement must be booked once in project initial items; disable period opening-purchase switches for this ledger"
                )
            service_cash = expense["total_eur"]
            if config.lifecycle:
                for year in observed:
                    subset = [r for r in rows if int(r["time"][:4]) == year]
                    service_by_year[year] = service_report(subset, config.service_economics)[
                        "views"
                    ]["expenditure"]["total_eur"]
    initial = sum(i.eur or 0 for i in scenario.items if i.category == "initial") + sum(
        a["lifecycle_opening_eur"] for a in observed.values()
    )
    years = []
    reference = list(sorted(observed))
    for y in range(1, scenario.life_years + 1):
        original = reference[(y - 1) % len(reference)]
        a = observed[original]
        scale = (8784 if calendar.isleap(original) else 8760) / a["hours"]
        inflation = (1 + scenario.inflation) ** y if scenario.price_basis == "nominal" else 1
        variable = (
            a["co2_kg"] * (scenario.co2_eur_per_kg or 0)
            + a["water_m3"] * (scenario.water_eur_per_m3 or 0)
            + a["consumables_eur"]
        ) * scale
        # Service cash is allocated over the observed reference span, separately disclosed.
        field = (
            service_by_year.get(original, 0)
            if config.lifecycle
            else service_cash / len(rows) * (8784 if calendar.isleap(original) else 8760)
        )
        lines = [
            *(
                [
                    dict(
                        name="Recorded lifecycle invoices in this chronological year",
                        eur=a["lifecycle_cash_eur"],
                    )
                ]
                if config.lifecycle
                else []
            ),
            dict(name="CO2, water, consumables and recorded interventions", eur=variable),
            dict(
                name="Recorded service expenditure in this chronological year"
                if config.lifecycle
                else "Recorded service expenditure, annual span average",
                eur=field,
            ),
        ]
        for item in scenario.items:
            if (
                item.category == "annual"
                or (item.category == "replacement" and item.year == y)
                or (item.category in ("decommissioning", "residual") and y == scenario.life_years)
            ):
                lines.append(
                    dict(
                        name=item.name,
                        eur=(item.eur or 0) * (-1 if item.category == "residual" else 1),
                    )
                )
        years.append(
            dict(
                reference_year=original,
                reference_hours=a["hours"],
                extrapolation_factor=scale,
                accepted_kg=a["accepted_kg"] * scale,
                gross_kg=a["gross_kg"] * scale,
                receipts_eur=a["accepted_kg"]
                * scale
                * (scenario.methane_eur_per_kg or 0)
                * inflation,
                cost_eur=sum(i["eur"] for i in lines) * inflation,
                operating_margin_eur=(
                    a["accepted_kg"] * scale * (scenario.methane_eur_per_kg or 0)
                    - variable
                    - field
                    - (a["lifecycle_cash_eur"] if config.lifecycle else 0)
                    - sum(i.eur or 0 for i in scenario.items if i.category == "annual")
                )
                * inflation,
                lines=lines,
            )
        )
    numerical = calculate(initial, years, scenario.discount_rate)
    unpriced = sorted(set(missing))
    if unpriced:
        numerical["known_subtotal_npv_eur"] = numerical.pop("npv_eur")
        numerical.update(
            npv_eur=None, levelised_eur_per_kg=None, simple_payback=None, discounted_payback=None
        )
    result = dict(
        schema_version="site-project-cashflow/1",
        study_id=study_id,
        case_id=case_id,
        physical_partition_hashes=[x["period_sha256"] for x in case["periods"]],
        dispatch_price_version=digest(config.to_dict()["costs"]),
        scenario=scenario.model_dump(mode="json"),
        price_version=digest(scenario.model_dump(mode="json")),
        initial_cash_eur=initial,
        unpriced=unpriced,
        expired_evidence=expired,
        status="incomplete-costs" if unpriced else "scenario-complete",
        partial_year_extrapolation=partial,
        **numerical,
        boundaries=[
            "Pre-tax, unlevered; scenario receipts are not certified sales",
            "Capital paid at year zero, replacements as cash; ownership/depreciation and usage wear are excluded",
            "Physical actions and original dispatch prices are unchanged",
            "Residual value reduces the levelised-cost numerator only when explicitly entered",
            "Zero accepted output has undefined unit cost",
            "Lifecycle cases use a fully recorded chronological path; recycling a lifecycle year is rejected"
            if config.lifecycle
            else "Repeating observed years does not simulate lifetime degradation or new faults",
        ],
    )
    return {"id": store.put("cashflow", result), **result}
