# Observed-performance benchmark

Open [the reviewed write-up](report.html). The 18 immutable study cases cover three explicit worlds, two seeds and three knowledge arms; each executes three dispatch strategies (54 traces). Inputs and outputs are in `results.json`, original editions in `latest.json`, and the scoped interpretation in `interpretation.json`.

Repeat with `.venv/bin/python -m research.observed-performance.run_benchmark` from the repository root. This creates new editions and updates the latest index; previous study inputs, attempts and reports remain saved. Change `fixture()` to define a new plant basis. The saved specifications identify joint draws, observation-estimator assumptions, solver budgets, original controller assumptions and weather snapshots. Inspect each study from Simulation menu → Studies, or use its original-source reproduction bundle.

The studies use the source frozen before dispatch. They do not establish calibration, guaranteed safety, a transferable robot capability, or an isolated controller-production benefit. Budget-sensitive numerical variation was visible even for matched nominal assumptions. See `docs/observed-performance.md` for current execution boundaries, including deferred private duration/logistics models and calibrated reliability learning.
