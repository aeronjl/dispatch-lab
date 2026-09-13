# Sites: product and engineering design

[Read the illustrated design](report.html). This is a design proposal, not an
implemented siting feature, screened land recommendation or annual methane study.
It contains a 39-source primary reference register, 19 proposed connector families,
repository integration review and three saved real PVGIS reference calculations.

## Evidence and scope

- `design.md` is the authored design; `sources.json` records reviewed primary links.
- `data-catalogue.json` records proposed data coverage, access and boundaries.
- `integration-inventory.json` identifies the inspected existing source files.
- `retrieval-20260913/` contains three successful public PVGIS 5.3 API requests,
  their raw JSON, exact parameters, retrieval metadata and SHA-256 values.
- The top-level `resource-samples.json` and `data/` preserve an earlier failed
  sandbox DNS attempt. They are not substituted into the successful-data example.
- `validation.json` checks artifact and raw-data integrity; `browser-validation.json`
  checks the isolated report. Neither qualifies any proposed app capability.

Provider PV output is for a 1 kWp reference array at existing city coordinates.
These are not available parcels or Dispatch Lab DC/methane forecasts. Winter share
is derived from the saved monthly means. There is no financial simulation here.
Only the PVcalc probe was live-tested. Other data connectors were researched from
primary documentation. Access plans, licences and adapter qualification remain
implementation work. External references can change after the review date.

## Rebuild and verify offline

From the repository root, with the existing Python and Node environments installed:

```sh
.venv/bin/python research/siting-design/sources.py
.venv/bin/python research/siting-design/catalogue.py
.venv/bin/python research/siting-design/build_report.py
.venv/bin/python research/siting-design/validate.py
node --check research/siting-design/report.js
node research/siting-design/check-browser.cjs
```

The builder uses the installed `markdown-it-py`; browser verification uses the
repository's pinned Playwright and installed Chromium. The report embeds the
small saved dataset and uses the existing local Departure Mono font. Reading and
interacting require no network. It is a directory artifact: preserve the CSS/JS,
JSON/raw files and referenced font alongside the HTML. Reviewed screenshots are
stored under ignored `build/siting-design/`, with hashes in browser validation.
External articles themselves are not included in this bundle.

For a new live data edition, choose a new output directory:

```sh
.venv/bin/python research/siting-design/fetch-resource-samples.py research/siting-design/retrieval-NEW-EDITION
```

This contacts only the public JRC PVGIS API, makes three small requests and does
not modify the plant app or submit site information to suppliers. Output manifests
use exclusive creation; do not overwrite a completed edition. A new edition is
not automatically selected by the report builder.
