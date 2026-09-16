# Equipment reference source review — 16 September 2026

This is a specification review supporting the equipment-planning workflow, not a
new calibration campaign. Exact download hashes and retrieval times are in
[downloads.json](downloads.json). Original PDFs are retained locally under `raw/`
and excluded from version control and shared reproduction bundles.

- [Trina TSM-NEG19RC.20, TSM_EN_2024_A](https://static.trinasolar.com/sites/default/files/Datasheet_210R_NEG19RC.20_EN_2024A_web.pdf), page 2: selected 600 W bin and temperature model inputs. Array assembly is assumed; no inferred bifacial gain or warranty-derived stochastic failure rate.
- [Enapter AEM Flex120, AEMFlex120-DTS-COM02_rev08](https://handbook.enapter.com/electrolyser/aem-flex120/downloads/Enapter_Datasheet_AEM-Flex-120_EN.pdf), page 2: nominal base-configuration figures and their stated test conditions. The separate nominal power, flow and specific-consumption figures do not exactly reconcile; that discrepancy stays visible in the model mapping.

The identified editions take precedence over undated product-name matching. Older
Enapter material in earlier research is not relabelled. The current reference is
not a service manual and does not establish repair capability, field performance,
system integration or installation costs.

See [the implementation contract](../../docs/equipment-planning.md) for the complete
scope, evidence workflow and remaining commissioning gates.
