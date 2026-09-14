# Living model workspace

Open **Model** in the simulation menu, **How it is modelled** in an inspector, or
**Trace calculation** beside inspector results. The full-screen reading workspace
contains twenty continuous illustrated essays. Reading, changing a learning example
and inspecting a recorded result are separate activities. Back/Escape restores the
originating view. No learning edit changes experiment setup or a source run.

The searchable index covers solar, battery, electrolysis, hydrogen, supplied CO₂,
thermal methanation, electrical coupling, forecasts, sensors/diagnosis, controllers,
economics, experiment interpretation, Sites and seven service topics: cleaning, referenced inspection, recovery, robot charging, finite logistics, service costs and observed duration uncertainty. Each essay combines authored explanation,
interactive inputs, Python-calculated output, assumptions and evidence. The original
plant artwork remains unchanged. Mobile readers get the example inline with its
active passage; reduced motion suppresses transitions and decorative motion.

## Extending an essay

`methane/model_topics.py` owns reviewed narrative, equation-term descriptions,
control definitions and model references. `methane/learning.py` provides bounded
teaching adapters over production kernels. Its fixtures are explicitly illustrative,
use fixed seeds and never receive the selected source run. The examples expose
production audits and use independent expectations in `tests/test_learning.py`.

`methane/documentation.py` joins that content to component contracts and source-bound
evidence. Numerical dependencies and narratives are fingerprinted. Changing a model
or narrative invalidates its review bindings and saved example outputs. After reviewing
the scientific meaning of the affected passages, refresh the bindings and fixtures:

```sh
uv run python -m methane.documentation review
uv run python -m methane.documentation examples
uv run python -m methane.documentation check
uv run python -m methane.catalogue generate
```

The review command records a review; it is not an automated scientific approval.
CI checks the bindings and fixtures but never automatically updates them.

## Interfaces and isolation

Three same-origin POST routes use a bounded run-context token:

- `/dispatch/model-document`: current or archived topic, with optional recorded lineage.
- `/dispatch/learning-example`: a small calculation with a topic and supported fixture inputs.
- `/dispatch/learning-job`: start, poll or cancel a bus/controller calculation in an isolated process.

Responses echo the request generation. The client rejects late results and displays
infeasible or incomplete inputs without relabelling an old result as the new answer.
Jobs are limited to one per context and two globally, use capped numerical-library
threads and terminate on cancellation. Cancellation also handles requests cancelled
before the start response arrives. Reading and simple calculations avoid the optimizer
queue. Source runs are accessed read-only; no request accepts executable code or paths.

The reactor example uses an explicitly described local heating/cooling policy. The bus
example uses the production execution allocator. The controller example uses real
Greedy/MPC planners and reports solver termination and fallback. Experiment-comparison
fixtures are labelled authored schedules, never misrepresented as controller results.

## Evidence and preservation

`This run` uses original documentation and recorded calculation identities. Old
archives without a snapshot say so. `Current model` uses the loaded implementation;
editable fixtures identify themselves as learning examples. Empirical plant calibration
remains unsupported. Historical reports are not promoted to evidence for another build.

New schema-3 archives add one documentation snapshot and saved default teaching outputs.
Existing result fields and archive readers retain their meanings. Reproduction bundles
include `model-report.html`, a readable index with linked saved examples and recorded
operands. [Offline Model reports](offline-model-reports.md) describes the paged files,
original/current source boundaries and integrity checks. No network is needed for
saved reading. Live recalculation requires the restored app.

To collect evidence for the exact source under test:

```sh
uv run python -m methane.catalogue stamp --directory build/model
uv run pytest -q --junitxml=build/model/pytest.xml
uv run python -m methane.documentation evidence
node --test tests/*.test.cjs
npm run test:browser
```

The interactive performance budget is p95 200 ms for simple changes and 10 ms rendering
on the reference fixture. Solver comparisons have explicit progress/cancellation rather
than an instantaneous-response claim. Comprehension walkthrough observations are kept
separately from automated test results; a developer walkthrough is not user research.

The service essays reuse production optical, acquisition, resource, pricing, duration,
charging and recovery interfaces. Charging and recovery use cancellable isolated
workers. Recorded service traces contain topic-specific operands and original record
paths; learning fixtures remain independent. Model-context changes preserve keyboard
focus. Original artwork files are unchanged.
