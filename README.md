# Dispatch Lab

An interactive experiment platform for planning remote, solar-powered methane
plants. Explore where to build, how to size equipment, and how autonomous
controllers respond to intermittent power, uncertain weather and equipment faults.

The model couples solar, batteries, electrolysis, hydrogen and CO₂ storage, and a
thermal methanator with simulated inspection, maintenance and recovery services.
Use it to:

- Compare plant designs and control policies on production, costs, downtime and
  resource use.
- Watch operation, inspect why a decision was made, and test alternatives using
  the information available at that moment.
- Save experiments and publish reports that retain their inputs, assumptions,
  weather snapshots and model versions.

## Run locally

Install [Git](https://git-scm.com/downloads) and
[uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
git clone https://github.com/aeronjl/dispatch-lab.git
cd dispatch-lab
uv sync --locked
uv run python app.py
```

`uv` installs Python 3.12 and the locked dependencies.
Open [localhost:7860](http://127.0.0.1:7860) when the server is ready. The first
launch calculates a reference experiment, so startup can take a few minutes.
Stop the server with **Ctrl+C**. If the port is occupied, use
`uv run python app.py --port 7861` and open the corresponding address.

For a quick look without calculating the reference experiment, start with the
included recording instead:

```sh
uv run python app.py --archive tests/fixtures/browser-demo-v2.json.gz
```

The recording and synthetic experiments work offline after installation. Fetching
new weather or site data requires internet access. Node.js is not needed to run the app.

## First experiment

Follow **Site → Build → Operate**: choose a location, configure the illustrated
equipment, then select weather and a controller. Start with the explicitly labelled
synthetic example to explore without downloading data. Play or step through the
result and select a component to inspect its state, decisions and costs.

See the [project guide](docs/plant-projects.md) for investigation, comparison and
reporting, or [agent control](docs/agent-control.md) for simulated operation through MCP.

## Reproduce and check

Saved runs and caches live under `runs/`, outside Git. Export reproduction bundles
from the app to preserve inputs, results and source. Open a saved `.json.gz`
recording with `uv run python app.py --archive PATH_TO_RECORDING`.

Playback preserves recorded actions; recalculation can differ when optimizers hit
their time limits. Historical research runs require their original artifacts—see
[preservation and reproduction](research/README.md).

Run Python tests with `uv run pytest -q`. The [engineering guide](docs/engineering.md)
covers the full verification workflow and numerical reproduction.

## Model scope

This is an hourly research and planning model, not a calibrated replica of an
operating plant or a live hardware controller. It combines public data with
explicit assumptions and uncertainty. CO₂ is supplied; direct-air capture and
gas-quality certification are outside the core model. Results are conditional on
the chosen equipment, service and economic assumptions.

Explore **How it is modelled** in the app or the [model documentation](docs/methane-model.md).
The [legacy hydrogen prototype](docs/legacy-hydrogen.md) has a separate guide.

The interface uses [Departure Mono](https://departuremono.com/) by Helena Zhang,
with its [SIL Open Font License](assets/fonts/OFL.txt) included.
