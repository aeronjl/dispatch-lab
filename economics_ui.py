"""Cost exploration UI, kept separate from physical simulation and control."""

import csv
import io
import json
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path

import gradio as gr
import plotly.graph_objects as go

from economics import (
    CATEGORIES,
    Costs,
    battery_study,
    cost_timeline,
    evaluate,
    physical_id,
    sensitivities,
)
from ui_theme import AMBER, BACKGROUND, COMPARISON, FONT, GRID, INK

ROOT = Path(__file__).resolve().parent
TEAL, ORANGE = AMBER, COMPARISON
COLORS = ["#ffa32d", "#dfc9a9", "#c87c30", "#9d8666", "#e4b76b", "#80613c", "#f7d6a0"]
# name, label, UI multiplier (fractions shown as percentages), minimum, step
GROUPS = {
    "Equipment & installation": [
        ("solar_eur_per_kw", "Solar hardware · €/kW", 1, 0, 50),
        ("battery_eur_per_kwh", "Battery cells · €/kWh", 1, 0, 20),
        ("battery_power_eur_per_kw", "Battery electronics · €/kW", 1, 0, 10),
        ("electrolyser_eur_per_kw", "Electrolyser system · €/kW", 1, 0, 50),
        ("installation_fraction", "Installation · % of hardware", 100, 0, 5),
        ("site_setup_eur", "Site setup · €", 1, 0, 5000),
    ],
    "Life & wear assumptions": [
        ("solar_years", "Solar allocation life · years", 1, 1, 1),
        ("other_equipment_years", "Other equipment/site life · years", 1, 1, 1),
        ("battery_calendar_years", "Cell calendar life · years", 1, 1, 1),
        ("battery_cycles", "Cell life · equivalent full cycles", 1, 1, 500),
        ("stack_share", "Stack · % of electrolyser cost", 100, 0, 5),
        ("stack_calendar_years", "Stack calendar life · years", 1, 1, 1),
        ("stack_operating_hours", "Stack life · operating hours", 1, 1, 5000),
        ("start_equivalent_hours", "Extra wear per start · equivalent hours", 1, 0, 1),
    ],
    "Operation & interventions": [
        ("fixed_opex_eur_per_year", "Standing operation · €/year", 1, 0, 1000),
        ("water_litres_per_kg", "Water input · litres/kg H₂", 1, 0, 1),
        ("water_eur_per_m3", "Water supply/treatment · €/m³", 1, 0, 1),
        ("consumables_eur_per_kg", "Other consumables · €/kg H₂", 1, 0, 0.01),
        ("repair_eur_per_incident", "Repair budget · €/fault", 1, 0, 100),
        ("visit_eur_per_incident", "Site visit budget · €/fault", 1, 0, 100),
    ],
}
FIELDS = [field for group in GROUPS.values() for field in group]

METHOD = """
### Read these figures as a cost experiment

Every default is an **illustrative EUR assumption**, not a supplier quote, market benchmark or
Rivan cost. The analysis applies costs to a completed physical run; changing prices does not alter
the controller. The plant still produces hydrogen only, with the same illustrative physics.

**Upfront investment** is the purchase of solar hardware, battery cells and power electronics,
the complete electrolyser, an installation percentage on that hardware, and a site setup allowance.
The stack is a share of the electrolyser price, not an additional purchase.

**Period allocated cost** includes capital consumed during the simulated hours and a cash operating
budget. For solar, power electronics, non-stack electrolyser equipment and site/installation,
capital use is purchase cost / assumed life × simulated hours / 8,760. This is straight-line,
undiscounted allocation with no salvage value. It is not a financing payment or cash bill.

**Battery cells and the electrolyser stack are counted once.** For each, we use the larger of:

- Calendar allowance: purchase cost / calendar years × simulated hours / 8,760.
- Usage allowance: purchase cost × fraction of assumed operating/cycle life consumed.

Battery equivalent full cycles = DC-bus discharge kWh / (battery capacity × discharge efficiency).
Stack effective hours = on-hours + starts × assumed extra hours per start. A start's wear allowance
is separate from the electrical energy it consumes. The default extra wear is zero because we have
not measured it. The **maximum** rule is a simple allocation proxy: it omits interactions, depth of
discharge, temperature and ageing history. It does not forecast actual replacements or degrade
physical capacity. Usage may matter even when it has not overtaken the calendar floor.

**Cash operating budget** = standing operation × period/8,760 + water + consumables + incident budget.
Standing operation bundles land, routine maintenance, staffing/monitoring and insurance. Water is
litres/kg × hydrogen / 1,000 × €/m³. One repair and visit budget is included if an injected capacity
fault begins inside this run. It is an assumed incident budget, not a model of payment or repair
timing. The injected fault still recovers according to the original physical scenario.

**No electricity purchase charge:** this is an owned-solar, off-grid plant. Solar capital is already
included. Curtailment, storage losses and start-up energy reduce output; adding another expense for
them would double-count the same energy. They are shown as physical diagnostics. Lost production
is not an extra invoice or automatically recoverable revenue.

**Period €/kg = period allocated cost / hydrogen produced.** It is undefined with zero production.
We do not extrapolate three days of weather into annual output or claim lifetime LCOH. Annual figures
are only the calendar capital/standing-cost budget implied by the input assumptions. They exclude
usage-driven acceleration, water, consumables and incidents. They are not an annual operating forecast.

Final battery inventory remains unvalued and is shown for both controllers. The sizing comparison
starts every candidate empty. Differences in final inventory still matter when comparing output
or interpreting incremental cost/kg. No hydrogen sale price, profit, tax, discounting, debt,
subsidies, water-capacity limit, compression, gas delivery or methane costs are modelled.

### Reference points for the structure

[H2A-Lite](https://www.nlr.gov/hydrogen/h2a-lite) separates capital, operating and performance inputs.
[SAM dispatch](https://samrepo.nlr.gov/help/battery_dispatch_fom.html) uses battery degradation
penalties in dispatch. These inform the structure; they do not validate our defaults or maximum rule.
[DOE alkaline electrolyser assumptions](https://www.energy.gov/cmei/fuels/technical-targets-liquid-alkaline-electrolysis)
also distinguish uninstalled equipment costs from installation.
"""


def config(values):
    try:
        return Costs(
            **{
                field[0]: float(value) / field[2]
                for field, value in zip(FIELDS, values, strict=True)
            }
        )
    except (TypeError, ValueError) as exc:
        raise gr.Error(f"Please check the cost assumptions: {exc}") from exc


def euro(value, decimals=0):
    return "—" if value is None else f"€{value:,.{decimals}f}"


def styled(fig, height=350):
    fig.update_layout(
        height=height,
        margin={"l": 20, "r": 20, "t": 30, "b": 45},
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        font={"family": FONT, "color": INK, "size": 11},
        legend={"orientation": "h", "y": -0.25, "x": 0},
        hoverlabel={"namelength": -1},
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor="#685032")
    fig.update_yaxes(gridcolor=GRID, zerolinecolor="#685032")
    return fig


def cards(costed):
    m, b = (costed["controllers"][n] for n in ("Forecast MPC", "Greedy"))
    data = [
        (
            "Upfront investment",
            euro(costed["capital"]["upfront_eur"]),
            "Both controllers · same plant",
        ),
        (
            "Allocated cost · this run",
            euro(m["allocated_cost_eur"]),
            f"{euro(b['allocated_cost_eur'])} with greedy",
        ),
        (
            "Cost / kg · this run",
            euro(m["period_eur_per_kg"], 2),
            f"{euro(b['period_eur_per_kg'], 2)} with greedy",
        ),
        (
            "Cash operating budget",
            euro(m["cash_opex_budget_eur"]),
            "For this run · excludes capital",
        ),
    ]
    return (
        '<div class="cards">'
        + "".join(
            f'<div class="card"><div class="label">{label}</div><div class="value" '
            f'style="font-size:22px">{value}</div><div class="compare">{sub}</div></div>'
            for label, value, sub in data
        )
        + "</div>"
    )


def breakdown(costed):
    fig = go.Figure()
    names = ["Greedy", "Forecast MPC"]
    for key, color in zip(CATEGORIES, COLORS, strict=True):
        fig.add_bar(
            y=names,
            x=[costed["controllers"][n]["buckets_eur"][key] for n in names],
            name=key,
            orientation="h",
            marker_color=color,
            hovertemplate="%{y}<br>€%{x:,.2f}<extra>%{fullData.name}</extra>",
        )
    fig.update_layout(barmode="stack")
    styled(fig, 330)
    fig.update_xaxes(title="Allocated cost across this run · EUR")
    return fig


def comparison(costed):
    m, b = (costed["controllers"][n] for n in ("Forecast MPC", "Greedy"))
    lines = [
        [
            key,
            euro(b["buckets_eur"][key], 2),
            euro(m["buckets_eur"][key], 2),
            f"€{m['buckets_eur'][key] - b['buckets_eur'][key]:+.2f}",
        ]
        for key in CATEGORIES
    ]
    lines += [
        [
            "Total allocated cost",
            euro(b["allocated_cost_eur"], 2),
            euro(m["allocated_cost_eur"], 2),
            f"€{m['allocated_cost_eur'] - b['allocated_cost_eur']:+.2f}",
        ],
        [
            "Hydrogen · kg",
            f"{b['hydrogen_kg']:.2f}",
            f"{m['hydrogen_kg']:.2f}",
            f"{m['hydrogen_kg'] - b['hydrogen_kg']:+.2f}",
        ],
        [
            "Battery at end · kWh",
            f"{b['final_battery_kwh']:.2f}",
            f"{m['final_battery_kwh']:.2f}",
            f"{m['final_battery_kwh'] - b['final_battery_kwh']:+.2f}",
        ],
    ]
    delta_h2 = m["hydrogen_kg"] - b["hydrogen_kg"]
    delta_cost = m["allocated_cost_eur"] - b["allocated_cost_eur"]
    text = (
        f"**MPC − greedy:** {delta_h2:+.2f} kg hydrogen and {euro(delta_cost, 2)} "
        "allocated cost difference. Costs are applied after the physical simulation; "
        "neither controller is optimising this cost model."
    )
    if abs(m["final_battery_kwh"] - b["final_battery_kwh"]) > 1:
        text += (
            " **Ending battery inventories differ.** These figures do not adjust for that value."
        )
    if m["initial_battery_kwh"] > 1:
        text += (
            f" Both start with {m['initial_battery_kwh']:.0f} kWh of stored electricity; "
            "its opening value is not charged. Use an empty battery for cleaner sizing comparisons."
        )
    return lines, text


def wear_table(costed):
    rows = []
    for name, c in costed["controllers"].items():
        a = c["allowances"]
        for prefix, label in (("battery", "Battery cells"), ("stack", "Electrolyser stack")):
            rows.append(
                [
                    name,
                    label,
                    euro(a[f"{prefix}_calendar_eur"], 2),
                    euro(a[f"{prefix}_usage_eur"], 2),
                    euro(a[f"{prefix}_charged_eur"], 2),
                ]
            )
    return rows


def sensitivity_plot(items):
    fig = go.Figure()
    if not items:
        fig.add_annotation(
            text="Cost per kg is undefined: this run produced no hydrogen.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
    else:
        for key, color, label in (
            ("min_delta", TEAL, "Lower outcome"),
            ("max_delta", ORANGE, "Higher outcome"),
        ):
            fig.add_bar(
                y=[i["label"] for i in items],
                x=[i[key] for i in items],
                orientation="h",
                marker_color=color,
                name=label,
                hovertemplate="%{y}<br>%{x:+.3f} €/kg<extra>%{fullData.name}</extra>",
            )
    fig.update_layout(barmode="relative")
    styled(fig, 420)
    fig.update_xaxes(title="Change in period €/kg · Forecast MPC")
    fig.update_yaxes(autorange="reversed", automargin=True)
    return fig


def archive(physical, costed, sensitivity, study=None):
    folder = ROOT / "runs"
    folder.mkdir(exist_ok=True)
    path = folder / f"costs-{uuid.uuid4().hex[:10]}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        contents = {
            "physical-run.json": physical,
            "economics.json": costed,
            "sensitivity.json": sensitivity,
        }
        if study is not None:
            contents["battery-study.json"] = study
        for filename, payload in contents.items():
            z.writestr(filename, json.dumps(payload, indent=2, allow_nan=False))
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["category", "greedy_eur", "forecast_mpc_eur"])
        writer.writerows(
            [
                k,
                costed["controllers"]["Greedy"]["buckets_eur"][k],
                costed["controllers"]["Forecast MPC"]["buckets_eur"][k],
            ]
            for k in CATEGORIES
        )
        z.writestr("period-costs.csv", stream.getvalue())
        if study is not None:
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=list(study["rows"][0]))
            writer.writeheader()
            writer.writerows(study["rows"])
            z.writestr("battery-comparison.csv", stream.getvalue())
        z.writestr("read-me.md", METHOD)
    return str(path)


def calculate(physical, *values):
    costs = config(values)
    costed = evaluate(physical, costs)
    sensitivity = sensitivities(physical, costs)
    table, text = comparison(costed)
    cap = costed["capital"]
    capital_rows = [[k, euro(v)] for k, v in cap["assets"].items()]
    capital_rows.append(["Total upfront investment", euro(cap["upfront_eur"])])
    fixed_note = (
        f"**Annual calendar capital + standing budget: "
        f"{euro(cap['calendar_plus_standing_eur_per_year'])}/year.** This is an input-based "
        "budget floor, excluding usage acceleration, production inputs and incidents. "
        "Annual hydrogen output is not estimated."
    )
    sensitivity_rows = [
        [
            i["label"],
            f"{i['low_input']:g} → {i['high_input']:g}",
            euro(i["low_input_eur_per_kg"], 3),
            euro(i["high_input_eur_per_kg"], 3),
        ]
        for i in sensitivity
    ]
    largest = sensitivity[0]["label"] if sensitivity else "None (zero production)"
    note = (
        f"**{costed['hours']:g}-hour cost allocation · {physical['scenario']['weather']} · "
        f"seed {physical['scenario']['seed']}.** "
        f"Largest sensitivity in the specified stress ranges: **{largest}**. "
        "All prices and lifetimes are illustrative. This is not annual LCOH or a profit forecast."
    )
    payload = {
        "physical": physical,
        "economics": costed,
        "sensitivity": sensitivity,
        "timeline": cost_timeline(physical, costs),
    }
    return (
        cards(costed),
        breakdown(costed),
        table,
        text,
        capital_rows,
        fixed_note,
        wear_table(costed),
        sensitivity_plot(sensitivity),
        sensitivity_rows,
        note,
        archive(physical, costed, sensitivity),
        payload,
    )


def run_sizing(physical, progress=gr.Progress(), *values):  # noqa: B008
    costs = config(values)
    study = battery_study(physical, costs, progress)
    fig = go.Figure()
    for name, color in (("Greedy", ORANGE), ("Forecast MPC", TEAL)):
        rows = [r for r in study["rows"] if r["controller"] == name]
        fig.add_scatter(
            x=[r["battery_kwh"] for r in rows],
            y=[r["period_eur_per_kg"] for r in rows],
            name=name,
            mode="lines+markers",
            line={"color": color},
            hovertemplate="Battery %{x:g} kWh<br>%{y:.3f} €/kg<extra>%{fullData.name}</extra>",
        )
    styled(fig, 350)
    fig.update_xaxes(title="Battery capacity · kWh")
    fig.update_yaxes(title="Allocated cost / kg in this period")
    table = [
        [
            f"{r['battery_kwh']:g}",
            r["controller"],
            euro(r["upfront_eur"]),
            euro(r["period_allocated_eur"], 2),
            f"{r['hydrogen_kg']:.2f}",
            euro(r["period_eur_per_kg"], 3),
            euro(r["eur_per_extra_kg"], 3),
            f"{r['final_battery_kwh']:.2f}",
            f"{r['curtailed_kwh']:.1f}",
        ]
        for r in study["rows"]
    ]
    fallback = sum(r["fallbacks"] for r in study["rows"])
    limited = sum(r["limited_solves"] for r in study["rows"])
    note = (
        f"**Completed: {len(study['candidates'])} battery sizes · "
        f"{physical['scenario']['days']} days · seed {physical['scenario']['seed']}.** "
        "Every candidate starts EMPTY, with identical weather, faults and other equipment. "
        "Battery power scales with capacity at the selected C-rate. "
        "Ending inventory is shown and remains unvalued. These are period comparisons, not an "
        f"annual optimal size. {fallback} fallbacks; {limited} time-limited solves. "
        "Incremental €/kg compares each size with no battery, and is undefined without extra output."
    )
    costed = evaluate(physical, costs)
    study["display_note"] = note
    return fig, table, note, archive(physical, costed, sensitivities(physical, costs), study), study


def validate_study(study, physical, *values):
    if (
        study is not None
        and study["source_run_id"] == physical_id(physical)
        and study["cost_assumptions"] == asdict(config(values))
    ):
        return study["display_note"], gr.DownloadButton(interactive=True)
    return (
        "**Sizing results need updating.** Run the comparison using the current cost assumptions "
        "and completed physical scenario.",
        gr.DownloadButton(interactive=False),
    )


# Keep API field order stable while grouping the visible inputs by physical component.
COST_SECTIONS = {
    "solar": ["solar_eur_per_kw", "solar_years"],
    "battery": [
        "battery_eur_per_kwh",
        "battery_power_eur_per_kw",
        "battery_calendar_years",
        "battery_cycles",
    ],
    "stack": [
        "electrolyser_eur_per_kw",
        "stack_share",
        "stack_calendar_years",
        "stack_operating_hours",
        "start_equivalent_hours",
        "repair_eur_per_incident",
        "visit_eur_per_incident",
    ],
    "shared": [
        "installation_fraction",
        "site_setup_eur",
        "other_equipment_years",
        "fixed_opex_eur_per_year",
    ],
    "hydrogen": ["water_litres_per_kg", "water_eur_per_m3", "consumables_eur_per_kg"],
}


def create_cost_inputs():
    defaults = asdict(Costs())
    return [
        gr.Number(
            defaults[key] * multiplier,
            label=label,
            minimum=minimum,
            step=1 if minimum > 0 else step,
            min_width=155,
            maximum=100 if key == "stack_share" else None,
            render=False,
        )
        for key, label, multiplier, minimum, step in FIELDS
    ]


def render_cost_inputs(widgets, section):
    by_key = {field[0]: widget for field, widget in zip(FIELDS, widgets, strict=True)}
    for key in COST_SECTIONS[section]:
        by_key[key].render()


def build_cost_panel(physical_state, initial, html_css, widgets, playback):
    defaults = asdict(Costs())
    values = [defaults[f[0]] * f[2] for f in FIELDS]
    initial_view = calculate(initial, *values)
    gr.Markdown(
        "### Cost analysis · completed run\n"
        "The component inspector follows the playhead. These reports cover the **whole run**. "
        "Edit prices and lifetimes in **Experiment setup**, alongside each component."
    )
    summary = gr.HTML(initial_view[0], css_template=html_css)
    status = gr.Markdown(initial_view[9], elem_id="cost-status")
    with gr.Tabs():
        with gr.Tab("Breakdown"):
            bar = gr.Plot(initial_view[1], show_label=False)
            with gr.Accordion("Upfront investment and annual budget", open=False):
                capital_table = gr.Dataframe(
                    initial_view[4],
                    headers=["Asset / allowance", "Upfront €"],
                    interactive=False,
                    show_label=False,
                )
                fixed_note = gr.Markdown(initial_view[5])
        with gr.Tab("Controllers"):
            compare_note = gr.Markdown(initial_view[3])
            comparison_table = gr.Dataframe(
                initial_view[2],
                headers=["Cost / outcome", "Greedy", "Forecast MPC", "MPC − greedy"],
                interactive=False,
                show_label=False,
                wrap=True,
            )
            gr.Markdown(
                "**Wear accounting:** calendar and usage estimates are alternatives. "
                "The larger is charged once; there is no second replacement charge."
            )
            wear = gr.Dataframe(
                initial_view[6],
                headers=["Controller", "Asset", "Calendar €", "Usage €", "Charged €"],
                interactive=False,
                show_label=False,
                wrap=True,
            )
        with gr.Tab("Sensitivity"):
            gr.Markdown(
                "Change one cost/life input from **50% to 150%** of its current value. "
                "Extra start wear spans **0 to at least 10 equivalent hours**. "
                "These are explicit stress tests, not confidence intervals. "
                "The physical schedule stays fixed. A flat result can reflect a calendar floor."
            )
            sensitivity_fig = gr.Plot(initial_view[7], show_label=False)
            sensitivity_table = gr.Dataframe(
                initial_view[8],
                headers=[
                    "Assumption",
                    "Input range (native units)",
                    "€/kg at low input",
                    "€/kg at high input",
                ],
                interactive=False,
                show_label=False,
                wrap=True,
            )
        with gr.Tab("Battery sizing"):
            gr.Markdown(
                "### What does extra storage buy?\n"
                "Compare five sizes around the selected battery capacity, including zero. "
                "This reruns both controllers and can take several seconds. "
                "Annual production is not extrapolated from these days."
            )
            size_button = gr.Button("Compare battery sizes →", variant="primary")
            sizing_note = gr.Markdown(
                "Run a sizing comparison using the completed plant scenario "
                "and current cost assumptions. All candidates will start empty."
            )
            size_plot = gr.Plot(show_label=False)
            size_table = gr.Dataframe(
                headers=[
                    "Battery kWh",
                    "Controller",
                    "Upfront €",
                    "Period €",
                    "H₂ kg",
                    "Period €/kg",
                    "€/extra kg vs 0",
                    "End battery kWh",
                    "Curtailment kWh",
                ],
                interactive=False,
                show_label=False,
                wrap=True,
            )
            size_download = gr.DownloadButton(
                "Download sizing study · CSV + JSON", interactive=False, size="sm"
            )
            sizing_state = gr.State(None)
        with gr.Tab("Method"):
            gr.Markdown(METHOD)
    download = gr.DownloadButton(
        "Download costs + assumptions · CSV + JSON", value=initial_view[10], size="sm"
    )
    cost_state = gr.State(initial_view[11])
    outputs = [
        summary,
        bar,
        comparison_table,
        compare_note,
        capital_table,
        fixed_note,
        wear,
        sensitivity_fig,
        sensitivity_table,
        status,
        download,
        cost_state,
    ]
    gr.on(
        triggers=[physical_state.change] + [w.change for w in widgets],
        fn=calculate,
        inputs=[physical_state, *widgets],
        outputs=outputs,
        trigger_mode="always_last",
        concurrency_limit=1,
        api_name="costs",
        show_progress="minimal",
    )
    gr.on(
        triggers=[physical_state.change] + [w.change for w in widgets],
        fn=lambda: (
            "**Sizing results need updating.** Run the comparison after changing "
            "cost assumptions or completing a new physical run.",
            gr.DownloadButton(interactive=False),
        ),
        outputs=[sizing_note, size_download],
        queue=False,
        api_name=False,
    )
    size_button.click(
        run_sizing,
        inputs=[physical_state, *widgets],
        outputs=[size_plot, size_table, sizing_note, size_download, sizing_state],
        concurrency_limit=1,
        concurrency_id="simulation",
        api_name="battery_sizing",
    )
    # A completed study provides a new, usable file; stale results are disabled above.
    sizing_state.change(
        validate_study,
        inputs=[sizing_state, physical_state, *widgets],
        outputs=[sizing_note, size_download],
        queue=False,
        api_name=False,
    )

    cost_state.change(
        lambda payload: gr.HTML(economics=payload["timeline"]),
        inputs=cost_state,
        outputs=playback,
        queue=False,
        api_name=False,
    )
