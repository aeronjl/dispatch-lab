"""Standalone scientific figures. Numeric inputs are saved analysis outputs."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib
except ModuleNotFoundError:
    # Optional isolated plotting installation; no change to application dependencies.
    sys.path.append("/tmp/dispatch-lab-calibration-libs")
    import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
OUT.mkdir(exist_ok=True)
AMBER = "#ffae47"
WHITE = "#e9e1d2"
DIM = "#ae9270"
TEAL = "#78c9bc"
BACK = "#20211f"
plt.rcParams.update(
    {
        "figure.facecolor": BACK,
        "axes.facecolor": BACK,
        "savefig.facecolor": BACK,
        "text.color": WHITE,
        "axes.labelcolor": WHITE,
        "xtick.color": DIM,
        "ytick.color": DIM,
        "axes.edgecolor": "#65523a",
        "grid.color": "#65523a",
        "grid.alpha": 0.3,
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 160,
        "axes.titleweight": "bold",
    }
)


def get(n):
    return json.loads((HERE / "analysis" / f"{n}.json").read_text())


def finish(fig, name):
    fig.tight_layout(pad=1.8)
    fig.savefig(
        OUT / f"{name}.png",
        bbox_inches="tight",
        metadata={
            "Description": "Dispatch Lab literature calibration; source and method in accompanying report."
        },
    )
    plt.close(fig)


p = get("pv")
fig, ax = plt.subplots(1, 2, figsize=(11.3, 4.1), gridspec_kw={"width_ratios": [1, 1.3]})
rows = [r for r in p["scores"] if r["split"] == "holdout_even_months"]
ax[0].barh(
    ["NOCT 45°C", "Fitted NOCT", "Published Faiman", "Fitted Faiman"],
    [r["rmse"] for r in rows],
    color=[DIM, DIM, TEAL, AMBER],
    height=0.58,
)
ax[0].invert_yaxis()
ax[0].set_xlim(0, 4)
ax[0].set_xlabel("Held-out temperature RMSE (K)")
ax[0].set_title("A wind term helps")
for i, r in enumerate(rows):
    ax[0].text(r["rmse"] + 0.04, i, f"{r['rmse']:.2f}", va="center", fontsize=10)
for label, color in [("NOCT45", DIM), ("fitted_Faiman", AMBER)]:
    vals = [r for r in p["monthly"] if r["model"] == label and r["split"] == "holdout"]
    ax[1].plot(
        [r["month"] for r in vals],
        [r["rmse"] for r in vals],
        marker="o",
        color=color,
        label="NOCT 45°C" if label == "NOCT45" else "Fitted Faiman",
    )
ax[1].set_xticks([2, 4, 6, 8, 10, 12], ["Feb", "Apr", "Jun", "Aug", "Oct", "Dec"])
ax[1].set_ylabel("RMSE (K)")
ax[1].set_title("Even months withheld")
ax[1].legend(frameon=False, fontsize=10)
ax[1].grid(axis="y")
finish(fig, "solar")

p = get("pem")
rows = p["holdout_plateaus"]
x = np.array([r["system_kw"] for r in rows])
y = np.array([r["flow_channel_kgph"] for r in rows])
params = next(
    r
    for r in p["scores"]
    if r["model"] == "parameters"
    and r["power_boundary"] == "system_power"
    and r["hydrogen_channel"] == "hydrogen_flow"
)
fig, ax = plt.subplots(1, 2, figsize=(11.3, 4.1))
xx = np.linspace(min(x), max(x), 100)
ax[0].scatter(x, y, color=AMBER, s=36, zorder=3, label="Withheld plateau means")
ax[0].plot(
    xx,
    xx * params["affine_kg_per_kwh"] + params["affine_kg_per_h"],
    color=AMBER,
    label="Fitted affine",
)
ax[0].plot(
    xx, xx / params["fitted_kwh_per_kg"], color=TEAL, linestyle="--", label="Fitted constant"
)
ax[0].plot(xx, xx / 55, color=DIM, linestyle=":", label="55 kWh/kg at system boundary")
ax[0].set_xlabel("Whole-system AC demand (kW)")
ax[0].set_ylabel("Hydrogen flow channel (kg/h)")
ax[0].set_title("One device, observed domain only")
ax[0].legend(frameon=False, fontsize=8.5)
order = np.argsort(x)
for key, c, label in [
    ("system_specific_measured_channel", AMBER, "AC system / measured flow"),
    ("stack_specific_measured_channel", TEAL, "DC stack / measured flow"),
]:
    ax[1].plot(x[order], np.array([r[key] for r in rows])[order], marker="o", color=c, label=label)
ax[1].set_xlabel("Whole-system AC demand (kW)")
ax[1].set_ylabel("Specific electricity (kWh/kg)")
ax[1].set_title("The accounting boundary changes the answer")
ax[1].legend(frameon=False, fontsize=8.5)
ax[1].grid(axis="y")
finish(fig, "electrolyser")

p = get("battery")
fig, ax = plt.subplots(figsize=(10.5, 3.8))
for year, (a, b, c) in enumerate(p["coefficients"], 1):
    x = np.linspace(0.15 if year < 4 else 0.1, 1, 150)
    eta = a * x / (b + x) + c * x
    ax.plot(x * 500, eta, color=[AMBER, TEAL, WHITE, DIM][year - 1], label=f"Year {year}")
ax.axhline(90, color=DIM, linestyle=":", alpha=0.8, label="Fixture 90% (different boundary)")
ax.set_ylim(70, 100)
ax.set_xlabel("AC power (kW; nominal 500)")
ax.set_ylabel("AC round-trip efficiency (%)")
ax.set_title("Published cycle fits • separate auxiliaries excluded")
ax.legend(frameon=False, ncol=3, fontsize=9)
ax.grid(axis="y")
finish(fig, "battery")

p = get("reactor")
df = pd.read_csv(HERE / "analysis/reactor-points.csv")
fig, ax = plt.subplots(figsize=(10.5, 3.8))
x = np.linspace(0, 40, 240)
y = p["baseline_c"] + p["increment_k"] * (
    1 - np.exp(-np.maximum(x - 5, 0) / p["effective_time_constant_minutes"])
)
ax.scatter(df.time_minutes, df.temperature_c, color=AMBER, s=30, label="Manual figure extraction")
ax.plot(x, y, color=TEAL, label="Descriptive first-order fit")
ax.axvline(5, color=DIM, ls=":", label="Feed-rate step")
ax.set_xlabel("Time in published experiment (min)")
ax.set_ylabel("Reactor temperature (°C)")
ax.set_title("Coolant inlet held at 310°C • τ ≈ 9.30 min")
ax.legend(frameon=False, ncol=3, fontsize=9)
ax.grid(axis="y")
finish(fig, "reactor")

p = get("derived")
rows = p["gas_storage"]
fig, ax = plt.subplots(1, 2, figsize=(11.3, 4.0))
xx = np.arange(len(rows))
usable = [r["usable_mass_kg"] for r in rows]
heel = [r["heel_kg"] for r in rows]
ax[0].bar(xx, usable, color=AMBER, label="Usable above 20 bar")
ax[0].bar(xx, heel, bottom=usable, color="#66523b", label="Pressure heel")
ax[0].set_xticks(xx, [str(r["max_pressure_bar_absolute"]) for r in rows])
ax[0].set_xlabel("Maximum absolute pressure (bar)")
ax[0].set_ylabel("Hydrogen inventory (kg)")
ax[0].set_ylim(0, 75)
ax[0].set_title("60 kg nominal is not 60 kg usable")
ax[0].legend(frameon=False, fontsize=9)
ax[1].bar(xx, [r["volume_m3"] for r in rows], color=TEAL)
ax[1].set_xticks(xx, [str(r["max_pressure_bar_absolute"]) for r in rows])
ax[1].set_xlabel("Maximum absolute pressure (bar)")
ax[1].set_ylabel("Internal volume for 60 kg nominal (m³)")
ax[1].set_title("Conditional examples at 20°C")
finish(fig, "storage")
