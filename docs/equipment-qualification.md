# Equipment and site qualification

Open **Equipment & evidence → Qualification**. The new workflow freezes a scoped
question, measurement boundary, reviewer rationale, chronological split and
acceptance criteria, then assesses original recorded operation. It does not fit
parameters or change a design. Authenticated records from the proposed installation
are still required to close the empirical qualification gate.

## Workflow and claims

1. Attach the equipment basis; run a design and import observations for that exact
   design in **Observed operation**. Preserve serials, measurement method, absolute
   uncertainty, timing and redistribution rights. The origin remains a supplied
   assertion; synthetic examples never become field evidence.
2. Define an assessment with development `[start, split)` and evaluation
   `[split, end)` hours from the case start. All bounds are integers, disjoint and
   inside a maximum 744-hour window. Name a reviewer and explain comparability of
   actual weather, commands, initial state and metering. Thresholds have no hidden
   defaults: the user supplies maximum RMSE and absolute bias, minimum paired-hour
   coverage and sample count. These are not manufacturer acceptance standards.
3. Freeze an immutable protocol before evaluating it. Previously visible results
   and measurements are not made blind by this action. No claim of preregistration,
   independent external validation or freedom from prior model-selection bias is
   established. The development subset is reported separately; nothing is fitted
   on it by this feature.
4. Evaluate committed intervals. Residual is simulated minus observed. Missing,
   suspect and not-yet-simulated hours stay missing and count in the full selected
   window denominator. Inadequate coverage/sample count makes the assessment
   incomplete. Failed comparability remains unsupported regardless of the numeric
   score. Adequately covered evaluation data can lie within or outside the declared
   numerical criteria; neither outcome is an overall readiness or trust score.
5. Inspect the largest absolute residuals through original interval links. This
   ordering identifies discrepancies, not their causes or causal importance.
   Publish an authored report and export its original measurements, protocol,
   comparison, study and implementation capsules. Partial results are preserved;
   later execution produces a new assessment edition rather than updating them.

The evaluator computes bias and RMSE independently for each subset. It also counts
residuals exceeding the supplied absolute measurement bound. It does not subtract
measurement uncertainty from residuals or use it to relax criteria. Those bounds
are not probability intervals, and model/input uncertainty is separate. A bound
larger than a tolerance is visibly flagged. Numerical agreement alone cannot
resolve unidentifiable parameters, correlated error or insufficient excitation.

## Measurement boundaries

The existing `electrolyser_kw` column retains its original meaning: productive
power **excluding startup** and external auxiliaries. The UI now states this
explicitly. Additional channels expose original process AC demand, DC island input,
electrolyser base AC input including startup, external cooling heat/electricity,
water consumed, end-of-hour water stock, end-of-hour reactor temperature and ambient
temperature. Thermal kW and electrical kW have distinct channel definitions.
Temperature channels accept negative values. Other channels remain nonnegative.

Interface channels are absent in older/non-integrated runs. They remain unavailable,
not zero or reconstructed from today's model. No implicit resampling, conversion,
interpolation or pressure/quality measurement model is added. A heat-duty observation
requires an independent measurement or documented calculation and uncertainty; the
model's assumed heat fraction is not measurement evidence.

## Evidence review · 16 September 2026

The [current evidence plan](equipment-evidence-plan.json) is shown on demand in the
workspace. It supplies targeted acquisition requests in order of consequence:
metering and identity; converter/cooler limits; process and thermal operation;
supplies and service logistics; commercial inputs. It is labelled as current
knowledge even while inspecting an old run, never as that run's original evidence.

Public sources were checked again:

- [Enapter Flex120 rev08](https://handbook.enapter.com/electrolyser/aem-flex120/downloads/Enapter_Datasheet_AEM-Flex-120_EN.pdf)
  supplies a nominal specification and conditions, not a measured cooler curve or
  commissioning trace. Cached search results and other manufacturer documents can
  contain older editions; this review preserves the exact selected edition.
- [JRC122565](https://publications.jrc.ec.europa.eu/repository/handle/JRC122565)
  provides guidance for defining electrolyser test boundaries, operating conditions
  and stressor tests across technologies. It supplies no measurements for this plant.
- [IEA PVPS / Sandia module validation data](https://pvpmc.sandia.gov/datasets/iea-pvps-task-13-module-validation-dataset/)
  contains measured outdoor and characterization data for other modules. The earlier
  local analysis is preserved with its original identities and time-label caveats.
  Its fitted parameters and outcomes do not qualify the selected Trina array.
- [Veatch et al.'s PEM data](https://datadryad.org/dataset/doi:10.5061/dryad.8931zcs64)
  is useful for studying power/flow measurement boundaries, but it is a different
  electrolysis technology and installation. It cannot calibrate the AEM reference.

No old study was rerun or relabelled, no manufacturer claim was treated as observed
performance, and no fabricated site data was imported. The next empirical step is
matching OEM/commissioning records. Any fitted adapter subsequently proposed needs
an identifiable mechanism, declared training data, independent evaluation and a
reviewed applicability envelope before adoption. That remains an explicit open gate.

## Verification receipt · 16 September 2026

Seventy-five focused Python checks passed across qualification, equipment evidence,
plant interfaces, report/export boundaries, site comparisons/workflows, operating
requirements and project revisions. All 98 JavaScript checks passed. Five selected
browser checks passed, including the full qualification journey and the unchanged
plant/solar screenshot references. After a small export-progress cleanup, the
qualification and stale-response journeys passed again (two checks). Desktop and
narrow-screen captures were visually reviewed; no baseline was changed.

Ruff lint/format checks, documentation freshness, the assumption inventory and
engineering documentation checks passed. The full Python/browser suites were not
rerun for this increment. Acceptance fixtures use synthetic measurements and test
software behaviour; they are not evidence of plant realism or participant usability.
