# Research records and artifact preservation

Git contains the authored research reports, source registries, protocols,
as-executed research scripts, interpretation, compact case summaries and selected
validation records. Reports remain readable without the full historical runs.
These are dated records: their evidence applies to the model and environment
identities they record, not automatically to the latest application.

## What is preserved separately

Large numerical runs, full per-interval audits, repeated source capsules, exported
reproduction ZIPs and their unpacked copies are retained locally and ignored by
Git. The `literature-calibration/raw/` directory contains downloaded third-party
papers, code and datasets; the source links, retrieval outcomes and SHA-256 values
are recorded in `literature-calibration/downloads.json`. Browser-generated
research screenshots are also ignored; reviewed application screenshot baselines
and numerical fixtures under `tests/` are tracked.

`local-artifacts.json` inventories the ignored research artifacts present at the
September 2026 repository catch-up, with relative paths, sizes and SHA-256 values.
It is a preservation inventory, not numerical validation or a backup of those
bytes. Existing study and integrity manifests remain unchanged. Application data
under `runs/` and generated work under `build/` also stay local; their identities
and relevant locations are recorded by the individual reports and study indexes.
They are not exhaustively inventoried here.

A fresh clone can run the application and its fixture-based tests, and can read
the committed reports. Links into ignored artifacts require the corresponding
local archive. Reproducing historical calculations offline requires restoring
their original raw inputs, source capsules and pinned environments first. A
current source checkout alone does not reproduce the original executable model.
The literature download utility may help retrieve inputs, but mutable or
unavailable upstream URLs cannot replace a verified original snapshot. Compare
restored bytes against their recorded hashes and report missing artifacts openly.

Nothing was deleted during the catch-up. These local artifacts still need a
separate durable backup before this machine or workspace is removed. Git commits,
including the artifact inventory, do not provide that backup.

## Continuing the work

Commit new authored findings, protocols and compact result indexes alongside the
implementation they discuss. Keep large runs in the existing archive workflow;
record their identifiers and hashes rather than committing regenerated source
trees or full playback exports. Preserve unsuccessful cases and original
judgements. New model versions, reruns and revised audits get new editions; do not
rewrite previous evidence to make it appear current.

Application linting excludes this directory so that old as-executed scripts and
third-party downloads are not silently reformatted. Each research programme's
README, protocol and environment requirements govern its reproduction. Run
relevant checks for new research tooling and retain their scope and outcome.

## Programmes

- [Autonomous management](autonomous-management/report.html)
- [Field robotics](field-robotics/report.html)
- [Field realism review](field-realism-review/README.md)
- [Model assumptions](model-assumptions/report.html)
- [Literature calibration](literature-calibration/README.md)
- [Observed performance](observed-performance/README.md)
- [Recovery, uncertainty and the cost of waiting](recovery-comparison/report.html)
- [Uncertainty and autonomy](uncertainty-autonomy/report.html)
