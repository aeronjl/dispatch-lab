# Literature calibration reference edition

Read [the self-contained report](report.html). It is a deeper follow-up to [the original assumptions review](../model-assumptions/report.html), with new fits and source-backed reference cases. No production configuration, capabilities, simulation UI or saved runs are modified by this research.

## Reproduce offline

From the repository root, with the existing Python environment:

```sh
.venv/bin/python research/literature-calibration/analyse.py
.venv/bin/python research/literature-calibration/records.py
.venv/bin/python research/literature-calibration/figures.py
.venv/bin/python research/literature-calibration/build_report.py
.venv/bin/python research/literature-calibration/validate.py
node research/literature-calibration/check-report.cjs
```

`analyse.py` needs NumPy, pandas and SciPy. Exact versions used are in `analysis/manifest.json`. The report builder uses markdown-it-py. Optional figure rebuilding uses Matplotlib 3.11.2; the original run installed it in `/tmp/dispatch-lab-calibration-libs` without altering app dependencies. Saved PNGs and HTML can be read without that dependency. For a clean standalone research environment, use `requirements.txt`; these are the versions actually executed. Browser checks use the repository's locked Playwright installation and installed Chromium. They do not start or touch the Gradio app.

Numerical reproduction is offline: every fitted data input is cached in `raw/` and identified by SHA256. Figures use calculated CSV/JSON outputs. `report.html` embeds the font and five plots, so copying that single file preserves readable text and figures; its optional local artifact links require the accompanying directory. External source links need a connection if opened. Neither reading the report nor running the calculations fetches them.

## Evidence boundaries

- `protocol.json` and `protocol-clarification.json` preserve the split/selection decisions made before fitting. They are not an externally registered protocol.
- Solar: a single Swiss module/site, alternating-month hold-out. The July→January exercise is a separate split. Power-model residuals are a check, not a held-out fit or annual-yield measurement.
- PEM: one day and device; first/second halves of long plateaus. Keep the original flow channels and electrical boundaries. The fit is not an independent equipment validation.
- Reactor: manual figure extraction, descriptive first-order fit, no held-out data. ±1 K perturbations measure digitization sensitivity, not experimental uncertainty.
- Battery: authors' published coefficients, not a new fit. Round-trip measurements do not identify directional efficiencies. No raw SCADA was acquired.
- NIST: independently supplied density test points and documented thermochemical coefficients. Physical reference verification does not certify pressure equipment or process conversion.
- Hardware: device-specific claims and support requirements, not universal robot failure or repair probabilities.

## Files

`reference-profiles.json` contains nine named research references, including measured fits, reproduced models and manufacturer-bound cases. They are not automatically loaded into the application. `coverage.json` maps all 19 original mechanism groups to the deeper evidence position. `sources.json` records 46 source entries and access limitations. `downloads.json` records successes and failures, URLs, retrieval times and input hashes.

`fetch.py` is an explicit acquisition utility, never called by analysis. Its manifests document original URLs. Some URLs redirect to updated content; retain the original hashes and edition when comparing results. Direct Dryad and local battery PDF retrieval failed; the author-linked repository supplied the PEM data, and the battery paper was read through the research browser. The SUPSI characterization file has a `.zip` filename but is the original XLSX returned by the source (content type and hash are retained).

`validation.json` reports scoped numerical, provenance and document checks. `browser-validation.json` reports desktop/mobile, navigation, reduced-motion and offline-display checks. Neither is an overall trust score or a claim that plant/robot performance is calibrated. No controller comparison, learned-policy training or paused programme queue was resumed.
