# Release 2: deployment and the service lifecycle

The [release report](report.html) is the user-facing completion record. Its numerical
claims refer to the published programme identities, not automatically to a future
application version. [Protocol](protocol.md) · [narrative review](narrative-review.md).

## Repeat the work

Use the repository's locked Python environment. The scripts are research tools,
not hidden additions to controller inputs. Run them from the repository root with
`PYTHONPATH=.`. No remote data is fetched by this programme.

- `programme.py --new --create-only` creates new Sites designs and study editions
  from the nine cached ERA5 weeks, the continuous London year and a saved forecast
  archive. It refuses a missing seasonal inventory. The new pointer identifies
  the editions; it does not replace earlier study files.
- `programme.py` executes/resumes the pointer's original captured source. Every
  committed period has a checkpoint. A monitor restart can attach to its existing
  worker; it never invents missing intervals. Creation and execution are separate.
- `analyse.py` independently checks completed cases and writes prefix/end-state
  receipts alongside the programme. It rejects a changed numerical/checker source.
- `observability.py` executes controlled-load identification examples. Those are
  mechanism demonstrations, not environmental samples or estimates of fault rates.
- `offline.py` captures and checks one new lifecycle run, its explanations and its
  source. Numerical rerunning uses the bundled `source/recompute.py` in a restored
  locked environment; recorded playback does not rerun decisions.
- `preserve.py` compares the six original-source historical repetitions. `--export --compact`
  produces portable ZIPs through the separately captured compact reader; `export_all.py` uses three independent reading processes; it adds no numerical
  solver worker. `restore_preservation.py` verifies full temporary
  extractions with the captured standalone checker under `python -I -S`.

The final report's receipts distinguish source integrity, numerical checks,
comparison evidence, UI checks and agent-authored comprehension review. No overall
trust score or empirical validation claim is assigned.

## Artifact boundary

Authored scripts, protocols, compact checks and interpretations belong in Git.
Original execution partitions, weather bytes, source capsules, large reports,
reproduction ZIPs and browser screenshots remain in the existing local stores.
Disposable extraction directories are removed after offline checks; their original
ZIPs and the check receipts remain. A commit is not a backup of these large artifacts.

Changing a plant, support resource, observation model or price affecting dispatch
requires a new design/edition. Repricing a fixed trace is separately labelled.
Training and learned policy deployment remain Release 3 work.

## Compact historical reader

The initial paged export was stopped after it demonstrated a million-file scaling
problem. Its partial file and receipt remain; it is not a valid bundle. The
compact exporter keeps every original edition file and recording, the original
explanations and saved examples, and every derived calculation object. It groups
calculation topics into one selectable page per controller/interval. It does not
run a model in the browser. The reader adapter is included in each bundle alongside
the separately identified production calculation source and original execution
source. `compact-preflight.json` compares calculation objects;
`compact-browser.json` records offline/narrow-screen interaction checks.

## Execution editions

The initial programme `4f06ad527fdd4457a540614fa35ab1ac` completed its 72 seasonal
cases and stopped at annual hour 1,337 after checkpoint profiling. Its study,
publication, qualification receipts and first-edition report remain preserved.
The active programme starts all 116 cases again under the corrected source;
`compare_editions.py` checks the seasonal traces and the available annual prefix.
`checkpoint_comparison.py` separately executes 24 hours from the same saved old
checkpoint under each source and reports complete physical/observation/service/
lifecycle record differences and timing. Neither comparison promotes old checks
as qualification of a new implementation. The current report's gates require
matching source identities, including its numerical, offline and observability
receipts. Build evidence directories are rolling aliases; the first-edition
artifact-location receipt names the preserved original copies.

The cross-edition helper's first draft used the Sites summary-row interface. That
interface deliberately omits requested actions and observation dictionaries. The
retained correction receipt limits the earlier comparison to the fields it actually
read; the version-2 helper reads full period records, requires every compared field
and reruns the available cases. The separate 24-hour compatibility experiment already
used complete run records. Summary projections are never evidence for omitted operands.
