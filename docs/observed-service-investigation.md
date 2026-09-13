# Observation-contingent service execution

`observed-service-investigation/1` connects the conditional investigation calculation to actual service requests. It is an opt-in, bounded execution policy, exposed through structured configuration and the recorded Site services view. It does not complete stage 4 of the field-operations roadmap.

An observed capacity incident opens an episode with one fixed deadline. The controller compares immediate qualified replacement with its declared fixed or mobile reader followed by a compatible remedy. It uses a private planning copy: rejected alternatives create no work order, stock reservation or backlog. Every positive-probability continuation must have a validated process incumbent, and the selected arm must meet the declared *assumed* restoration probability. Unresolved or unpriced comparisons remain unresolved.

Only the selected present request enters the real executive. Its registered recipe, resources and current power are rechecked with dock and process planning. The first request starts at the boundary assumed by the comparison; delayed or combined starts are not presented as the same prediction. Current operational feasibility still governs execution and fallbacks.

For this policy, `commissioned-contact-evidence/1` counts explicitly requested readers. Installing a second reader does not require waiting for a reading never commissioned. If two readers are commissioned in the incident, both must settle under the existing reference, age and disagreement rules. Older policies retain their configured-reader aggregation and archived meanings.

The actual eligible contact finding determines the next action. A closed contact permits a bounded reset; an open contact calls for qualified replacement. An interrupted inspection provides no fabricated measurement. Unsupported, ambiguous or overdue findings retain uncertainty and can require escalation. A successful-looking inspection never upgrades process capacity.

The original static prior becomes inapplicable after physical intervention. It is not silently renewed. Opt-in `bounded-post-service-followup/2` extends the existing repeated-test tracker to resets. Actual resource-feasible tracking shortfalls can justify a separate qualified substitution, under the original deadline and finite intervention budget. Only the process observer confirms recovery. Inspection completion, procedure completion and operating confirmation remain distinct. New unrelated diagnostic incident counts cannot restart an unresolved capacity episode's deadline.

## Configuration and preservation

`Config.investigation_policy` and dispatch policy version 4 freeze the reader, comparison mode, prior, noise quadrature, risk weight, minimum assumed restoration probability and observation wait. Configuration and policy round trips retain these fields. Older configurations omit the new optional field. Advanced field setup now has an optional investigation editor inside coordinated services. It exposes the reader, strategy, follow-through version, risk, minimum assumed restoration probability, comparison budget and observation wait. It preserves any original custom prior and states the illustrative default explicitly. Version 2 requires joint recovery version 2 and coordinated service version 3; incompatible configuration remains a visible error. Saved examples remain available through their playback.

The modes are `planned`, `inspect-first` and `direct-intervention`. The latter two are explicit comparison arms, subject to the same declared eligibility requirement. `methane.services.investigation_runs.fixture` supplies the documented execution cases. Generate a new recording directory with:

```sh
.venv/bin/python -m methane.services.investigation_runs --directory build/services/my-new-investigation-edition
```

The writer refuses to replace a nonempty directory. Each case retains original configuration, source, requested/applied actions, findings, tests, conditional comparison, costs and ending inventories. The report links to recorded animation, numerical results and a self-contained reproduction bundle. Playback renders a compact selection summary with a path to the full original calculation; it does not recalculate the comparison.

## Checked execution cases

Source `aa562f6618f9c3e292290e6ceb359225c8a86624133d554e16c8f95f830cc622`. The [seven-case report](../build/services/investigation-integration/recorded/first-check/report.html) uses 32-hour, seed-7 fixtures with illustrative constant power and an explicit power-shortage variant. Reader noise is zero and compatible procedure success is assumed to be one. These are workflow examples, not measured reliability or general controller rankings.

| Case | Methane / kg | Final capacity estimate / kW | Investigation result |
|---|---:|---:|---|
| Trip, inspect first | 234.481 | 450 | Confirmed H18 |
| Damage with stuck contact, inspect first | 223.909 | 450 | Confirmed H26 |
| Same damage, direct replacement | 236.909 | 450 | Confirmed H19 |
| Trip, planned selection | 240.909 | 450 | Confirmed H19 |
| Unreadable reader | 249.091 | 225 | Escalation |
| Late evidence | 253.909 | 225 | Escalation; no complete investigation fits the comparison horizon |
| Power shortage during verification | 143.201 | 360 | Escalation; full capacity remains unconfirmed |

In the matched damage pair, direct replacement confirms recovery seven hours earlier and produces 13 kg more methane. Inspect-first first tries a reset because the shared contact reports closed; repeated operating tests then support replacement. Both cases record €530 service expenditure. Total allocated costs differ (€1,542.84 inspect-first, €1,548.53 direct) because physical usage differs; the direct case's assumed contribution is €7.32 higher. No price or fault truth is changed between the pair.

The unresolved cases can produce more methane within this short window than a recovered case. That does not make their ending health equivalent. Continuing to use derated equipment, test activity, inventory constraints and the reporting boundary all matter. Longer matched studies and terminal health/work requirements remain necessary.

Verification: 128 final-source targeted Python tests, 66 JavaScript tests and 67 browser checks pass; 13 optional browser fixtures are skipped. An earlier full run passed 801 tests and failed two worker-identity checks while the example writer's import was corrected; the final targeted run includes both checks and passes. The only source change between those runs is the example writer's import. This is not reported as a clean full-suite run at the final source.

All seven archives pass 31,938 independent checks in aggregate and their restored, dependency-free offline bundle checks. Both damage cases also have networking-disabled numerical reruns from captured source: all 32 applied intervals match, with zero methane and allocated-cost deltas. Other cases have offline integrity/physics verification at this checkpoint, not numerical reruns. Original plant, solar and existing Model screenshot references are unchanged. New report and revealed investigation views were checked on desktop and narrow screens with keyboard return and reduced motion. The sampled Model interaction p95 is 84 ms and rendering p95 is 0.5 ms; active-batch performance is not claimed.

## Remaining boundaries

The original version-1 conditional calculation retains its historical prediction semantics. Opt-in version 2 now nominates a continuation from an actual finding and rechecks work, charging and operating tests jointly; see [Observed continuation](investigation-continuation.md). Dynamic belief transitions, broader uncertainty models, terminal reserve/health studies, original-information investigation-selection what-ifs and interpreted multi-seed Studies remain required. Existing process/service alternatives preserve the recorded accepted work/test prerequisite; they do not choose a different investigation strategy. The rest of the six-stage programme, including all unfinished hardware mechanisms, service essays, degradation and held-out learned/homeostatic policies, remains in scope.
