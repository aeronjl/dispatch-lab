"""Local-only Gradio playground. Run with: uv run python app.py"""

import argparse
import csv
import io
import json
import os
import time
import uuid
import zipfile
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import gradio as gr
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from economics_ui import build_cost_panel
from experiment import Scenario, run_experiment
from plant import Plant

ROOT = Path(__file__).resolve().parent
TEAL, ORANGE, INK, GRID = "#087f73", "#cb713c", "#233a35", "#e8eae4"
CSS = """
.gradio-container {max-width: 1500px !important; padding: 28px 32px !important;}
body {background: #f6f6f0 !important;}
footer {display: none !important;}
#settings {background: white; border: 1px solid #e2e7df; border-radius: 16px; padding: 22px;}
#settings .block {border: 0; box-shadow: none;}
#settings h3 {font-size: 15px; color: #233a35; margin-top: 10px;}
#run {min-height: 46px; font-weight: 650; border-radius: 10px;}
#results .block {border-radius: 12px;}
#timeseries {border: 1px solid #e2e7df; background: #fff; border-radius: 16px;}
#run-note {font-size: 12px; padding: 0 4px; color: #60746e;}
.tabitem {padding: 18px 4px !important;}
@media(max-width: 800px) {.gradio-container {padding: 16px !important;}}
"""
HTML_CSS = """
* {box-sizing: border-box;}
.eyebrow {font: 650 11px system-ui; letter-spacing: 1.8px; color: #527269;}
.topline {display: flex; justify-content: space-between; gap: 12px; align-items: center;}
.badge {border: 1px solid #d5dfd5; color: #527269; padding: 6px 11px; border-radius: 25px;
        font: 550 11px system-ui; letter-spacing: .5px; white-space: nowrap;}
h1 {font: 550 38px system-ui; letter-spacing: -1.7px; color: #233a35; margin: 12px 0 8px;}
.intro {font: 15px/1.6 system-ui; color: #60746e; max-width: 840px; margin: 0 0 20px;}
.flow {display: flex; align-items: center; gap: 14px; padding: 16px 20px;
       border: 1px solid #dfe6dd; border-radius: 12px; background: #edf2e9; margin-bottom: 10px;}
.node {flex: 1; color: #233a35; font: 600 13px system-ui;}
.node small {display: block; font: 12px system-ui; color: #60746e; margin-top: 4px;}
.arrow {color: #7d998d;}
.cards {display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 6px;}
.card {padding: 17px; border: 1px solid #e2e7df; border-radius: 12px; background: #fff;}
.label {font: 600 10px system-ui; letter-spacing: 1px; color: #60746e; text-transform: uppercase;}
.value {font: 550 27px system-ui; letter-spacing: -.8px; color: #087f73; margin: 9px 0 7px;}
.value span {font-size: 12px; font-weight: 400; letter-spacing: 0;}
.compare {font: 12px/1.5 system-ui; color: #cb713c;}
.insight {border-left: 3px solid #8fb8a2; padding: 12px 16px; background: #edf2e9;
          color: #35544b; font: 13px/1.6 system-ui; border-radius: 0 10px 10px 0;}
.insight b {font-weight: 650;}
.legend {display: flex; gap: 18px; font: 12px system-ui; color: #60746e; padding: 8px 0;}
.legend span {display: flex; align-items: center; gap: 6px;}
.dot {height: 8px; width: 8px; border-radius: 50%; display: inline-block;}
@media(max-width: 1000px) {.cards {grid-template-columns: repeat(2, 1fr);}}
@media(max-width: 600px) {h1 {font-size: 30px;} .flow {gap: 6px; padding: 12px;}
 .node {font-size: 11px;} .node small {font-size: 10px;} .badge {display: none;}}
"""

HEADER = """
<div class="topline"><div class="eyebrow">AUTONOMOUS PLANTS / EXPERIMENT 001</div>
<span class="badge">LOCAL LAB · SYNTHETIC DATA</span></div>
<h1>When should a solar plant run?</h1>
<p class="intro">Give a small hydrogen plant a battery and a weather forecast. Compare a
simple rule with a controller that plans ahead. Follow the energy, inspect the costs,
and find which assumptions deserve attention.</p>
<div class="flow">
 <div class="node">01 · Solar array<small>Intermittent electricity</small></div>
 <span class="arrow">→</span>
 <div class="node">02 · DC bus + battery<small>Use electricity now or store it</small></div>
 <span class="arrow">→</span>
 <div class="node">03 · Electrolyser<small>Minimum load + start-up energy → H₂</small></div>
</div>
"""

ASSUMPTIONS = """
### What this toy represents

An **off-grid DC bus** connecting solar, a battery and an electrolyser. Each step is one hour.
It produces **hydrogen**, not methane. There is no location-specific calibration or Rivan plant data.

- Solar is a synthetic daylight curve with seeded, correlated cloud variation. Changing daylight
  explores seasons in a simplified way; it is not a European irradiance forecast.
- Battery charge and discharge efficiency are each √0.90 (90% round trip). Power is limited by
  capacity × C-rate. There is no simultaneous charging and discharging, degradation or self-discharge.
- The electrolyser has a fixed **55 kWh of productive electricity per kg H₂**. Every start adds
  the selected electrical overhead. This overhead is consumed inside the hour, without a warm-up
  delay. Minimum load is a fraction of nameplate capacity, even when the plant is derated.
- A fault reduces available electrolyser capacity. Both controllers observe that capacity in the
  affected hour. This tests response to a known limit, **not sensor-based fault detection**.
- No gas inventory, water/CO₂ supply limits, compression, heat balance, ramp rates, idle loads,
  power electronics or grid constraints are included in the physics. A separate cost layer
  allocates illustrative capital and operating costs after the run; it does not alter dispatch.

These are adjustable, illustrative assumptions. The next scientific step is to replace them with
equipment curves and validate against data. This is a control sandbox, not a calibrated digital twin.

### The controllers

**Greedy:** produce as much hydrogen as current PV and stored electricity allow; store any surplus.
This baseline uses the battery and obeys the same start-up costs and operating limits as MPC.

**Forecast MPC:** solve a mixed-integer linear programme each hour and execute its first production
decision. The objective is total forecast hydrogen output, with a tiny (0.001%) battery-throughput
penalty to break ties. It includes minimum load, starts, storage losses and power limits.
Stored energy at the end of the planning horizon has zero salvage value. Short horizons can
therefore encourage premature discharge. The final experiment horizon is clipped to the run end.

The forecast combines a known synthetic weather template with only the **current observed** cloud
error, decaying over three hours. Forecast bias affects future hours. Current-hour mean PV is treated
as measured: an hourly scheduling abstraction. Future realised weather and future fault timing are
never passed to the controller. During a fault, MPC assumes the currently observed capacity persists
until it observes a change. There is no uncertainty optimisation or learned policy yet.

Each solve has a 0.5-second limit and a 0.1% objective-gap tolerance. Feasible time-limited schedules
are marked; missing/invalid solutions fall back to the greedy rule. Counts appear in Run details.

### Check the accounting

`PV energy = productive electricity + start-up electricity + curtailed energy
 + battery losses + change in stored energy`

Hydrogen is `productive electricity / 55`. Battery charging power is measured at the DC bus.
Utilisation is productive energy divided by nameplate electrolyser power × experiment duration.
It includes nights and fault hours in the denominator. Both strategies start with identical inventory.
Final inventory is reported separately; a production delta is not an inventory-adjusted economic return.

### Where the implementation comes from

The physics is explicit in `plant.py`; scheduling is in `controllers.py`; weather and paired runs
are in `experiment.py`. The UI is separate in `app.py`.

[SciPy / HiGHS mixed-integer solver](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)
 · [Gradio](https://www.gradio.app/) · [Plotly Python](https://plotly.com/python/)
"""


def cards_and_insight(result):
    m, b = (result["metrics"][name] for name in ("Forecast MPC", "Greedy"))
    pv = m["pv_kwh"]
    curtailed = 100 * m["curtailed_kwh"] / pv if pv else 0
    baseline_curtailment = 100 * b["curtailed_kwh"] / pv if pv else 0
    cards = [
        (
            "Hydrogen produced",
            f"{m['hydrogen_kg']:,.1f}",
            "kg H₂",
            f"{b['hydrogen_kg']:,.1f} kg with greedy",
        ),
        ("Solar curtailed", f"{curtailed:.1f}", "%", f"{baseline_curtailment:.1f}% with greedy"),
        ("Electrolyser starts", str(m["starts"]), "starts", f"{b['starts']} with greedy"),
        (
            "Battery at finish",
            f"{m['final_battery_kwh']:,.0f}",
            "kWh",
            f"{b['final_battery_kwh']:,.0f} kWh with greedy",
        ),
    ]
    html = (
        '<div class="cards">'
        + "".join(
            f'<div class="card"><div class="label">{label}</div><div class="value">'
            f'{value} <span>{unit}</span></div><div class="compare">{comparison}</div></div>'
            for label, value, unit, comparison in cards
        )
        + "</div>"
    )
    delta = m["hydrogen_kg"] - b["hydrogen_kg"]
    if abs(delta) < 0.05:
        headline = "Planning and the simple rule produce essentially the same hydrogen here."
    else:
        direction = "more" if delta > 0 else "less"
        headline = f"Planning produces {abs(delta):.1f} kg {direction} hydrogen in this run."
    if abs(m["final_battery_kwh"] - b["final_battery_kwh"]) > 1:
        detail = (
            "Final battery inventories differ; compare those before interpreting the output gap."
        )
    elif delta < -0.05:
        detail = (
            "Extra starts, forecast error and a finite planning horizon can outweigh the benefit "
            "of looking ahead. Inspect the traces, then change one assumption."
        )
    else:
        detail = (
            "Try removing storage or raising the start-up energy. A useful control problem "
            "emerges when these constraints change the best decision."
        )
    insight = f'<div class="insight"><b>{headline}</b><br>{detail}</div>'
    return html, insight


def plot_traces(result):
    rows = result["records"]
    n = len(rows["Greedy"])
    x = list(range(n + 1))
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.095,
        subplot_titles=(
            "Power at the plant",
            "Electricity in the battery",
            "Hydrogen produced so far",
        ),
    )
    pv = [r["pv_kw"] for r in rows["Greedy"]]
    fig.add_trace(
        go.Scatter(
            x=x,
            y=pv + [pv[-1]],
            name="Available solar",
            mode="lines",
            line={"color": "#bac7b6", "width": 1, "shape": "hv"},
            fill="tozeroy",
            fillcolor="rgba(183, 199, 173, 0.28)",
            hovertemplate="Hour %{x}<br>Solar: %{y:.0f} kW<extra></extra>",
        ),
        row=1,
        col=1,
    )
    for name, color, dash in (("Greedy", ORANGE, "dash"), ("Forecast MPC", TEAL, "solid")):
        series = rows[name]
        power = [r["electrical_demand_kw"] for r in series]
        common = {
            "name": name,
            "legendgroup": name,
            "mode": "lines",
            "line": {"color": color, "width": 2.4, "dash": dash},
        }
        fig.add_trace(
            go.Scatter(
                x=x,
                y=power + [power[-1]],
                **common,
                line_shape="hv",
                hovertemplate="Hour %{x}<br>Demand: %{y:.0f} kW<extra>%{fullData.name}</extra>",
            ),
            row=1,
            col=1,
        )
        initial = result["metrics"][name]["initial_battery_kwh"]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=[initial] + [r["battery_kwh"] for r in series],
                **common,
                showlegend=False,
                hovertemplate="Hour %{x}<br>Stored: %{y:.1f} kWh<extra>%{fullData.name}</extra>",
            ),
            row=2,
            col=1,
        )
        cumulative = [0.0] + np.cumsum([r["h2_kg"] for r in series]).tolist()
        fig.add_trace(
            go.Scatter(
                x=x,
                y=cumulative,
                **common,
                showlegend=False,
                hovertemplate="Hour %{x}<br>Hydrogen: %{y:.1f} kg<extra>%{fullData.name}</extra>",
            ),
            row=3,
            col=1,
        )
    fig.update_annotations(font={"size": 13, "color": INK}, x=0, xanchor="left")
    s = result["scenario"]
    if s["fault_capacity_fraction"] < 1 and s["fault_start_hour"] < n:
        for row in (1, 2, 3):
            fig.add_vrect(
                x0=s["fault_start_hour"],
                x1=min(n, s["fault_start_hour"] + s["fault_duration_hours"]),
                fillcolor="#d77b54",
                opacity=0.11,
                line_width=0,
                row=row,
                col=1,
            )
        fig.add_annotation(
            x=s["fault_start_hour"],
            y=1.04,
            xref="x",
            yref="paper",
            text="Capacity fault",
            showarrow=False,
            xanchor="left",
            font={"color": ORANGE, "size": 11},
        )
    fig.update_layout(
        height=670,
        margin={"l": 55, "r": 25, "t": 90, "b": 35},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
        font={"family": "system-ui, sans-serif", "size": 11, "color": INK},
        legend={"orientation": "h", "y": 1.13, "x": 0},
        dragmode="zoom",
        uirevision=str(uuid.uuid4()),
    )
    fig.update_xaxes(
        range=[0, n],
        gridcolor=GRID,
        zeroline=False,
        tickmode="array",
        tickvals=list(range(0, n + 1, 12 if n <= 72 else 24)),
    )
    for row, title in ((1, "kW"), (2, "kWh"), (3, "kg H₂")):
        fig.update_yaxes(
            title_text=title, rangemode="tozero", gridcolor=GRID, zeroline=False, row=row, col=1
        )
    fig.update_xaxes(title_text="Hours since midnight at the start of day 1", row=3, col=1)
    return fig


def ledger(result):
    fields = [
        ("Available solar", "pv_kwh"),
        ("→ Productive electricity", "productive_kwh"),
        ("→ Start-up electricity", "startup_kwh"),
        ("→ Curtailed electricity", "curtailed_kwh"),
        ("→ Battery losses", "battery_loss_kwh"),
        ("→ Change in stored electricity", "battery_change_kwh"),
    ]
    return [
        [label] + [round(result["metrics"][name][key], 3) for name in ("Greedy", "Forecast MPC")]
        for label, key in fields
    ]


def run_details(result):
    p, s = result["plant"], result["scenario"]
    m, b = (result["metrics"][name] for name in ("Forecast MPC", "Greedy"))
    loss = 100 * (1 - s["fault_capacity_fraction"])
    fault = (
        f"{loss:.0f}% capacity loss from hour {s['fault_start_hour']} for "
        f"{s['fault_duration_hours']} hours"
        if loss
        else "None"
    )
    return f"""**This run:** {s["days"]} days · seed {s["seed"]} · {s["weather"]} ·
{s["horizon_hours"]}-hour planning horizon · {s["forecast_bias"]:+.0%} forecast bias.

**Equipment:** {p["solar_kw"]:,.0f} kW solar · {p["battery_kwh"]:,.0f} kWh battery
({p["battery_kwh"] * p["battery_c_rate"]:,.0f} kW limit) · {p["electrolyser_kw"]:,.0f} kW electrolyser.
Minimum load {p["min_load_fraction"]:.0%}; start-up energy {p["start_energy_kwh"]:,.0f} kWh.
Initial battery: {p["initial_soc"]:.0%} for both controllers. **Fault:** {fault}.

| Check | Greedy | Forecast MPC |
|---|---:|---:|
| Electrolyser utilisation | {b["utilisation"]:.1%} | {m["utilisation"]:.1%} |
| Battery throughput (bus kWh) | {b["battery_throughput_kwh"]:,.1f} | {m["battery_throughput_kwh"]:,.1f} |
| Largest hourly energy residual (kWh) | {b["max_balance_error_kwh"]:.2e} | {m["max_balance_error_kwh"]:.2e} |

**Solver:** {m["solver_seconds"]:.2f} seconds in total · {m["limited_solves"]} time-limited
feasible solutions · {m["fallbacks"]} fallbacks. The solver accepts a 0.1% objective gap.

The download contains hourly traces for both strategies and the complete parameters, metrics,
model version and solver statuses. Identical seeds reproduce the weather. Time-limited solves
may differ across machines; this is one scenario, not a statistical performance estimate.
"""


def export_run(result):
    target = ROOT / "runs"
    target.mkdir(exist_ok=True)
    path = target / f"dispatch-{uuid.uuid4().hex[:10]}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("experiment.json", json.dumps(result, indent=2, allow_nan=False))
        stream = io.StringIO()
        names = ["controller"] + list(result["records"]["Greedy"][0])
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        for name, rows in result["records"].items():
            writer.writerows({"controller": name, **r} for r in rows)
        archive.writestr("hourly-traces.csv", stream.getvalue())
    return str(path)


def present(result, elapsed):
    cards, insight = cards_and_insight(result)
    s, p = result["scenario"], result["plant"]
    note = (
        f"Results: **{s['days']} days · {s['weather']} · seed {s['seed']}** — "
        f"{p['solar_kw']:,.0f} kW solar / {p['battery_kwh']:,.0f} kWh battery / "
        f"{p['electrolyser_kw']:,.0f} kW electrolyser. Completed in {elapsed:.1f}s."
    )
    return (
        cards,
        insight,
        plot_traces(result),
        ledger(result),
        run_details(result),
        export_run(result),
        note,
        result,
    )


def simulate(
    solar,
    battery,
    electrolyser,
    weather,
    days,
    variability,
    bias,
    horizon,
    start_energy,
    minimum_load,
    c_rate,
    daylight,
    initial_soc,
    fault_loss,
    fault_start,
    fault_duration,
    seed,
    progress=gr.Progress(),  # noqa: B008 - Gradio injects progress via a default parameter.
):
    plant = Plant(
        solar_kw=solar,
        battery_kwh=battery,
        electrolyser_kw=electrolyser,
        min_load_fraction=minimum_load / 100,
        start_energy_kwh=start_energy,
        battery_c_rate=c_rate,
        initial_soc=initial_soc / 100,
    )
    scenario = Scenario(
        days=int(days),
        weather=weather,
        variability=variability,
        forecast_bias=bias / 100,
        horizon_hours=int(horizon),
        daylight_hours=daylight,
        fault_capacity_fraction=1 - fault_loss / 100,
        fault_start_hour=int(fault_start),
        fault_duration_hours=int(fault_duration),
        seed=int(seed),
    )
    started = time.perf_counter()
    result = run_experiment(plant, scenario, progress)
    return present(result, time.perf_counter() - started)


PRESETS = {
    "01 · Broken clouds": [
        1000,
        800,
        450,
        "Broken clouds",
        3,
        0.25,
        0,
        24,
        40,
        30,
        0.5,
        12,
        0,
        0,
        34,
        8,
        7,
    ],
    "02 · No battery": [
        1000,
        0,
        450,
        "Broken clouds",
        3,
        0.25,
        0,
        24,
        40,
        30,
        0.5,
        12,
        0,
        0,
        34,
        8,
        7,
    ],
    "03 · Expensive restarts": [
        1000,
        800,
        450,
        "Broken clouds",
        3,
        0.25,
        0,
        24,
        140,
        30,
        0.5,
        12,
        0,
        0,
        34,
        8,
        7,
    ],
    "04 · A capacity fault": [
        1000,
        800,
        450,
        "Broken clouds",
        3,
        0.25,
        0,
        24,
        40,
        30,
        0.5,
        12,
        0,
        70,
        34,
        8,
        7,
    ],
    "05 · The forecast is wrong": [
        1000,
        800,
        450,
        "Broken clouds",
        3,
        0.25,
        50,
        24,
        40,
        30,
        0.5,
        12,
        0,
        0,
        34,
        8,
        7,
    ],
    "06 · Clear, predictable days": [
        1000,
        800,
        450,
        "Clear days",
        3,
        0,
        0,
        24,
        40,
        30,
        0.5,
        12,
        0,
        0,
        34,
        8,
        7,
    ],
}


def build_app():
    default = simulate(*next(iter(PRESETS.values())), progress=None)
    with gr.Blocks(title="Dispatch lab · Autonomous plants", analytics_enabled=False) as demo:
        physical_state = gr.State(default[7])
        gr.HTML(HEADER, css_template=HTML_CSS)
        with gr.Row(equal_height=False):
            with gr.Column(scale=1, min_width=290, elem_id="settings"):
                gr.Markdown("### Set up an experiment")
                preset = gr.Dropdown(
                    list(PRESETS), value=next(iter(PRESETS)), label="Start with a scenario"
                )
                solar = gr.Slider(0, 2000, value=1000, step=50, label="Solar array · kW")
                battery = gr.Slider(0, 4000, value=800, step=100, label="Battery capacity · kWh")
                electrolyser = gr.Slider(
                    100, 1200, value=450, step=50, label="Electrolyser capacity · kW"
                )
                run = gr.Button("Run experiment →", variant="primary", elem_id="run")
                gr.Markdown(
                    "Adjust a setting, then run. Both controllers receive the same conditions."
                )
                with gr.Accordion("Weather & foresight", open=False):
                    weather = gr.Dropdown(
                        ["Clear days", "Broken clouds", "Passing front"],
                        value="Broken clouds",
                        label="Weather pattern",
                    )
                    with gr.Row():
                        days = gr.Dropdown([2, 3, 5, 10], value=3, label="Days", min_width=90)
                        horizon = gr.Dropdown(
                            [6, 12, 24, 48], value=24, label="Look ahead · h", min_width=110
                        )
                    variability = gr.Slider(
                        0,
                        0.6,
                        value=0.25,
                        step=0.05,
                        label="Cloud variability",
                        info="0 = predictable; larger = noisier weather",
                    )
                    bias = gr.Slider(
                        -60,
                        60,
                        value=0,
                        step=10,
                        label="Forecast bias · %",
                        info="Positive = overestimate future sunlight",
                    )
                with gr.Accordion("Equipment assumptions", open=False):
                    start_energy = gr.Slider(
                        0, 200, value=40, step=10, label="Energy per start · kWh"
                    )
                    minimum_load = gr.Slider(5, 80, value=30, step=5, label="Minimum load · %")
                    c_rate = gr.Slider(
                        0.1,
                        2,
                        value=0.5,
                        step=0.1,
                        label="Battery power · C-rate",
                        info="0.5 × capacity = maximum charge/discharge power",
                    )
                    daylight = gr.Slider(6, 18, value=12, step=1, label="Daylight · hours")
                    initial_soc = gr.Slider(0, 100, value=0, step=10, label="Initial battery · %")
                with gr.Accordion("Inject a fault", open=False):
                    fault_loss = gr.Slider(
                        0,
                        100,
                        value=0,
                        step=10,
                        label="Electrolyser capacity lost · %",
                        info="0 = no fault",
                    )
                    fault_start = gr.Slider(0, 47, value=34, step=1, label="Start at hour")
                    fault_duration = gr.Slider(1, 24, value=8, step=1, label="Duration · hours")
                seed = gr.Number(
                    value=7, minimum=0, maximum=999999, precision=0, label="Weather seed"
                )
            with gr.Column(scale=3, min_width=540, elem_id="results"):
                note = gr.Markdown(default[6], elem_id="run-note")
                with gr.Tabs(selected="costs"):
                    with gr.Tab("Plant operation", id="operation"):
                        cards = gr.HTML(default[0], css_template=HTML_CSS)
                        insight = gr.HTML(default[1], css_template=HTML_CSS)
                        plot = gr.Plot(default[2], show_label=False, elem_id="timeseries")
                        with gr.Tabs():
                            with gr.Tab("Energy ledger"):
                                gr.Markdown(
                                    "Every available solar kWh must go somewhere. The five destination "
                                    "rows sum to the solar input. **All values are kWh.**"
                                )
                                table = gr.Dataframe(
                                    default[3],
                                    headers=["Energy flow", "Greedy", "Forecast MPC"],
                                    datatype=["str", "number", "number"],
                                    interactive=False,
                                    show_label=False,
                                )
                            with gr.Tab("Run details"):
                                details = gr.Markdown(default[4])
                            with gr.Tab("Model & assumptions"):
                                gr.Markdown(ASSUMPTIONS)
                            with gr.Tab("Try this next"):
                                gr.Markdown("""### Four useful experiments

1. **Remove the battery.** Keep the same weather seed. Which lost solar hours can no controller recover?
2. **Raise start-up energy.** Inspect whether conserving battery energy can avoid an expensive restart.
3. **Make the forecast optimistic.** Compare the same plant and weather. Does planning still help?
4. **Inject a capacity loss.** Watch storage fill, curtailment rise and production recover.

Then repeat with several weather seeds. One attractive trace is not evidence of a better controller.
The first result worth pursuing is a repeatable improvement attributable to a physical constraint.
""")
                        download = gr.DownloadButton(
                            "Download physical run · CSV + JSON", value=default[5], size="sm"
                        )
                    with gr.Tab("Costs & trade-offs", id="costs"):
                        build_cost_panel(physical_state, default[7], HTML_CSS)
        inputs = [
            solar,
            battery,
            electrolyser,
            weather,
            days,
            variability,
            bias,
            horizon,
            start_energy,
            minimum_load,
            c_rate,
            daylight,
            initial_soc,
            fault_loss,
            fault_start,
            fault_duration,
            seed,
        ]
        outputs = [cards, insight, plot, table, details, download, note, physical_state]
        preset.change(
            lambda name: PRESETS[name], inputs=preset, outputs=inputs, queue=False, api_name=False
        )
        gr.on(
            triggers=[component.change for component in inputs],
            fn=lambda: (
                "**Settings changed.** Results below are from the last completed run. "
                "Press **Run experiment** to apply these settings."
            ),
            outputs=note,
            queue=False,
            api_name=False,
        )
        run.click(
            simulate,
            inputs,
            outputs,
            concurrency_limit=1,
            concurrency_id="simulation",
            api_name="simulate",
        )
    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Dispatch lab on localhost.")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    theme = gr.themes.Base(
        primary_hue="teal",
        secondary_hue="orange",
        neutral_hue="stone",
        font=["system-ui", "sans-serif"],
    )
    build_app().queue(max_size=8).launch(
        server_name="127.0.0.1",
        server_port=args.port,
        share=False,
        inbrowser=False,
        show_error=True,
        theme=theme,
        css=CSS,
        js="document.body.classList.remove('dark'); "
        "document.body.style.backgroundColor = '#f6f6f0';",
        footer_links=[],
    )
