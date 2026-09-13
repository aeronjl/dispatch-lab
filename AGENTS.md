# Working agreement

## Commit completed work

The user has authorised local commits as the default workflow. Commit completed,
verified increments without asking for permission again. For larger tasks, make
coherent intermediate commits at usable checkpoints instead of accumulating all
work until the end. Inspect the staged diff and run checks appropriate to each
change; include code, tests and applicable documentation together. Use descriptive
commit messages, and report any checks that could not be completed.

Preserve unrelated changes and existing history. Do not automatically push,
rewrite commits, or delete ignored evidence. A local commit is not a remote backup.
Record material unfinished work honestly rather than presenting a checkpoint as a
completed feature.

## Preserve the model and evidence

Keep the simulation's quiet presentation, Departure Mono styling and reviewed
plant/solar illustrations. Updating screenshot baselines requires an intentional
visual review.

Keep observations, estimates, predictions and simulator truth distinct. Never
relabel an old experiment or its validation as evidence for a new source version.
Use new result editions when rerunning experiments. Research artifact handling is
documented in `research/README.md`; ignored runs and source bundles stay on disk.

## Verification

Install Python dependencies with `uv sync --locked`. Application checks are
`uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q` and
`node --test tests/*.test.cjs`. Browser checks use `npm ci`, an installed Playwright
Chromium, and `npm run test:browser`. See `docs/engineering.md` and
`.github/workflows/checks.yml` for documentation, formal, offline and performance
checks. Use meaningful checks appropriate to the change; report their scope.

Historical research scripts retain their as-executed form and are outside the
application Ruff scope. Their protocols, environments and evidence identities
remain the authority for reproducing those studies.
