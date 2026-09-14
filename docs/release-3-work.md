# Release 3 implementation record

The authorised scope is the complete experiment platform in [release-3.md](release-3.md).
Large scientific campaigns remain optional. Work proceeds in usable local commits:

1. Frozen observation datasets, episode splits and reproducible estimator protocols.
2. Contained, versioned planning aids and explicit homeostatic reserve comparisons.
3. Sites training/evaluation workflow, Model explanations and portable artifacts.
4. Bounded workers, end-to-end acceptance and updated completion accounting.

Acceptance uses named small cases, including missing data and failed predictions.
Participant comprehension needs real participants; the software can provide the
protocol, capture and issue tracking, but cannot supply their answers. No durable
off-machine backup destination has been supplied. These two external requirements
will remain visible in the release accounting.

Checkpoint 1: observation datasets and fixed/adaptive/ridge comparisons are implemented.
Six focused checks passed for split boundaries, future-information separation,
missing/censored channels, fitted-domain rejection and cancellation.

Checkpoint 2: data-only registered policies and saturating reserve preferences run
through the original dispatch/execution constraints. Four policy checks and 67
existing physics/control/service checks passed together (71 total). A mixed legacy /
current HiGHS thread-initialisation failure was reproduced and fixed by consistently
using one numerical solver thread. The current provenance records that choice;
old recordings and source capsules retain their original solver assumptions.

The Sites interface, portable artifacts and full release qualification remain in
progress. These checkpoints are not evidence of field performance or completion.
