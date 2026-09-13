# Battery component example

The battery is the first component with execution, planning, generated reference
documentation, interchangeable implementations and displayed-result lineage.
The [generated specification](components.md#battery) is the source for units,
parameter bounds, assumptions, interfaces and verification entry points.

## Boundaries

`methane/battery.py` imports neither the plant nor SciPy, Gradio, weather or storage.
Its immutable state, inputs and parameters can be used without the application.
`BatteryKernel` is the structural replacement interface. `Battery` validates inputs
and checks the returned state, limits, exclusive flow and energy balance at runtime.
There is no global mutable implementation selection.

Planning emits linear rows using local ports. The adapter in `dispatch.build`
maps these to plant variables; shared electrical balance, objectives and dispatch
remain plant responsibilities. The execution adapter in `physics.transition`
calls the selected battery and uses its energy and losses in site accounting.
The economic wear allowance remains in `costing`, with its existing meaning.

Both implementations represent the same constant-efficiency model:

- `affine/1` retains the direct state equation.
- `loss-ledger/1` separately accounts for energy entering/leaving the bus and cells,
  and supplies an equivalent planning equation scaled by one-way efficiency.

The shared planning-row assembly handles indexing and exclusive direction; the
two kernels provide their own physical coefficients. The tests independently
construct and solve a battery-only optimization problem from this public contract.
Swapping to a different physical model would require a new model version and
new verification, not merely renaming an implementation.

## Running and replacing

```python
from methane.battery import Battery, BatteryInput, BatteryParameters, BatteryState
from methane.config import Config, Models
from methane.simulation import run

battery = Battery(BatteryParameters(200, 1, 0.64))
result = battery.step(BatteryState(20), BatteryInput(100, 0, 0.5))
assert abs(result.state.energy_kwh - 60) < 1e-8

run_result = run(Config(models=Models(battery="loss-ledger/1")))
```

In the app, open Experiment setup → Operating dynamics → Electrical and hydrogen
to select an implementation. The choice is frozen in configuration and provenance
and follows planning, execution, solver fallback, recovery probes and what-ifs.
Unknown implementation IDs fail explicitly. Historical configurations without
this field retain the original `affine/1` behaviour for new calculations.

Run the isolated fixture and checks:

```sh
uv run python -m methane.engineering component battery
uv run pytest tests/test_battery.py -q
uv run python -m methane.engineering docs --check
uv run python -m methane.mutations
uv run python app.py --archive runs/methane-v2/RUN_ID.json.gz
```

The fixture writes `build/engineering/battery.json`, including both executed
round-trip examples, hand-calculated expected values, source identity and timing.
Time-limited plant solvers may select different equivalent incumbents when
constraint scaling/order changes. Numerical component equivalence does not promise
identical controller actions or methane totals in every rerun.

## Following a displayed result

Click the battery → Now → **Trace this result**. A new run's end-of-interval
energy, SOC and loss figures link to the previous stored energy, applied charge
and discharge, duration, capacity and efficiency. The trace includes requested
power, the original decision path, asset ID, physical checks, implementation/model
versions and recorded source hashes. Rendering/rounding conventions are explicit.

`methane.battery_trace.trace(run, controller, decision_hour)` produces this lineage
in Python. It reads recorded evidence and does not rerun optimization or substitute
current numerical results. JSON-pointer paths address the source archive; prior
energy points to the previous interval or the initial capacity/SOC inputs.
The inspector fetches it with its recorded decision and rejects replies for a
different run/controller/hour. The full-screen view and illustration are unchanged.

Battery records (`dispatch-lab/battery-record/1`) and lineage
(`dispatch-lab/battery-lineage/1`) are additive fields in methane schema 3.
Old battery energy/loss columns retain their meanings. Existing archives are not
rewritten; missing battery lineage is explicitly unavailable. Repricing preserves
the physical record and model selection. Archive auditing recomputes physical
accounting and checks component-record inputs, outputs, identity and audits, even
if an altered archive has been re-sealed.

Hashes establish content identity, not authorship or empirical calibration.
Independent arithmetic, randomized tests and runtime audits verify this bounded
model; they do not prove that it describes a real battery or all possible future
implementations. Thermal effects, degradation and self-discharge remain unmodelled.
