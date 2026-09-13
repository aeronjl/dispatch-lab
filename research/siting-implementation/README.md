# Sites implementation qualification

The implementation connects candidate evidence, deployment designs, continuous
operation, project cash flow, finite comparisons and original playback. Open
**Sites** in the running application. [Usage and contract boundaries](../../docs/sites/implementation.md).

`report.html` is the compact user-facing release record. `validation.json` names
its executed source identities and evidence files; it does not transfer evidence
from an older run to a new build. The full saved numerical studies, source capsules,
raw weather and offline bundles remain in `build/siting-qualification/store` and
are also imported append-only into `runs/sites` for application access.

The three original 2025 anchor runs used the first execution implementation. A
fresh London year and a three-controller archived-Seville service example used the
subsequent execution implementation. The final process-visibility fix changes
status reporting only and has its own regression check. Original runs are never
relabelled as if rerun after that change.

This is an hourly numerical and workflow qualification. It does not calibrate
hardware, weather conversion, faults or maintenance, certify output, establish
land rights or replace quotes. The Seville comparison uses controller packages
with different documented recovery behaviour and tight numerical budgets, not a
claim that predictive control beats a local rule. Country-specific commercial and
hazard evidence still requires identified imports or access to its proper provider.

Reproduce a study by opening its frozen record and choosing **New numerical
repetition**. Reproduction ZIPs include permitted source inputs and source capsules.
Use `python -m methane.siting.reporting restore FILE.zip --root NEW_STORE` for
verified offline restoration. Compare original and recomputed traces as separate
editions. Run the targeted checks with `pytest -q tests/test_siting_*.py`; the full
application regression and browser commands remain in `AGENTS.md`.
