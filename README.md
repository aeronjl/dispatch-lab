# Dispatch lab

A local Python playground for solar–battery–electrolyser scheduling. Compare a
greedy operating rule with a receding-horizon mixed-integer controller (MPC),
using the same synthetic weather, initial inventory and equipment limits.

The **Costs & trade-offs** tab adds an explanatory cost layer: upfront investment,
costs allocated to the completed period, standing and variable operating budgets,
wear assumptions, controller comparisons, sensitivity tests and battery sizing.
Every cost default is an illustrative EUR assumption. Cost edits do not change
the physical schedule or either controller's objective.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
git clone git@github.com:aeronjl/dispatch-lab.git
cd dispatch-lab
uv sync --locked
uv run python app.py
```

Open http://127.0.0.1:7860. The server binds to loopback only, with sharing and
Gradio analytics disabled. Once dependencies are installed, simulation requires
no weather API, account or network connection. `Ctrl-C` stops the server.

Python 3.12 is required. `uv.lock` pins the environment. Downloaded runs are in
`runs/` and contain a JSON record and CSV time series. They can be deleted.
Cost and sizing downloads include the exact cost inputs, accounting method,
sensitivity ranges and complete physical traces for sizing candidates.

## What to try

Start with “Broken clouds”, then remove the battery. Raise start-up energy,
increase forecast bias, or inject a capacity fault. Change one assumption at a
time and keep the weather seed fixed for paired comparisons. Repeat over seeds
before making claims about a controller. Ten-day runs are available, but start
with three days to make individual decisions visible.

## Model boundary

This is an hourly control experiment, **not a calibrated Rivan digital twin**.
Output is hydrogen, with illustrative 55 kWh/kg productive electricity, an
adjustable electrical start-up overhead, and minimum operating load. There are
no gas or thermal dynamics, price signals, grid connection, physical ageing,
water limits, compressors or methane production. All defaults are assumptions.

The battery has finite capacity, power and charging/discharging losses. Energy
is explicitly conserved. The DC-bus identity for each step is:

```text
PV energy = productive electricity + start-up electricity + curtailment
            + battery losses + change in stored energy
```

The MPC sees the current observed PV and capacity plus a synthetic forecast.
It does not see future realised weather or fault timing. Current-hour average
PV is treated as measured, an explicit hourly abstraction. There is no fault
diagnosis; the available equipment capacity is assumed observable immediately.

The objective is forecast hydrogen output, with a tiny battery-throughput
tie-break. End-of-horizon battery energy has zero salvage value. Reported final
inventories must be considered alongside production differences. A 0.5-second
solver time limit and 0.1% objective gap keep interaction quick; feasible
time-limited solutions and fallback counts are reported. The initial battery
is identical for both strategies. The greedy baseline can use the battery.

## Structure

- `plant.py`: physical state and one-step energy accounting.
- `controllers.py`: greedy rule and MILP planning, using SciPy/HiGHS.
- `experiment.py`: synthetic weather, causal forecasts, faults and paired runs.
- `app.py`: Gradio controls, Plotly charts, comparison and downloads.
- `economics.py`: period cost allocation, capital, sensitivity and paired sizing.
- `economics_ui.py`: cost controls, comparisons, charts and reproducible exports.
- `tests/`: analytical energy checks, operating limits, causality and fallback.

There is one canonical physical model shared by both controllers. Research code
does not depend on Gradio, so policies and experiments can also run from scripts
or notebooks.

## Validate

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

The tests include a hand-solvable scheduling problem with a 180 kWh optimum,
battery round-trip efficiency, start-up overhead, fault limits, zero-energy
behaviour, forecast causality and identical pre-fault decisions. They validate
internal consistency, not accuracy against real equipment.

## Cost accounting

Upfront investment and period capital allocation are separate views, not amounts
to add together. Fixed capital allocation is cost / assumed years × hours / 8,760.
For replaceable battery cells and stacks, we charge the larger of calendar and
usage-based allocation once. Usage is an explicit proxy for consumption of an
assumed cycle/operating life; it does not simulate ageing, replacements or payment
timing. Installation and site costs are separate from hardware. The stack is a
share of electrolyser cost, not an additional purchase.

Cash operating budget comprises prorated standing costs, water/consumables and
one repair/visit budget if an injected capacity fault starts during the run.
Owned solar has no second electricity purchase charge; curtailed electricity,
losses and start energy affect output rather than creating duplicate invoices.

Period €/kg is undefined with zero output. Annual figures are only the calendar
capital plus standing-cost budget; annual hydrogen output is not inferred from
the short weather sample. No financing, taxes, subsidies or revenue are modelled.
Opening and closing battery inventories are shown without a monetary valuation.
The sizing comparison starts every candidate empty, holds weather/other equipment
fixed, and scales battery power with energy capacity at the selected C-rate.

Cost sensitivities stress one input from 50% to 150% of its current value, except
extra wear per start (0 to at least 10 equivalent hours). These are scenario
ranges, not confidence intervals. Cost and sizing exports record these choices.

## Implementation references

- [SciPy `milp`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)
- [HiGHS](https://highs.dev/)
- [Gradio Blocks](https://www.gradio.app/guides/blocks-and-event-listeners)
- [Plotly subplots](https://plotly.com/python/subplots/)
