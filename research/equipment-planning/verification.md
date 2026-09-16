# Software verification — 16 September 2026

Scope: equipment planning, plant projects, operating requirements, chronological
siting production/reporting, and the affected browser workflows. This is software
acceptance evidence; no field data or participant usability evidence is supplied.

- 45 targeted Python tests passed across equipment planning, requirements, projects,
  siting workflow, production and summary accounting. The export test was then
  rerun with additional assertions that only commissioning evidence available at
  run creation is included; it passed.
- 98 JavaScript tests passed.
- 21 browser checks passed; three checks requiring separately enabled fixtures
  were skipped. This included unchanged plant and solar screenshot baselines,
  playback, lazy disclosures, requirements, projects, responsive access and stale
  response protection. The two equipment browser tests were rerun after the final
  saved-comparison lookup change; both passed.
- Ruff lint/format, documentation freshness and diff whitespace checks passed.
- Desktop equipment-basis/comparison and narrow-screen captures were visually
  reviewed in `build/equipment-*.png`; no baseline images were replaced.

Early browser checks found inert-state inheritance on the new modal and a shared
status selector collision. Both were corrected. Missing-data accounting initially
failed to retain simulated values at absent observation timestamps; the bounded
window now retains them and marks the observations absent. Final checks passed.

The full repository Python/browser matrix and long research campaigns were not
rerun. No production kernel was changed. Existing ignored runs, downloads and
historical validation editions were preserved. Actual commissioning data, external
expert walkthroughs, OEM compatibility, hardware control, calibrated performance,
and off-machine backup remain outside this verification.
