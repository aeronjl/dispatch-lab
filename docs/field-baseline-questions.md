# Six baseline questions for field operations

The first recovery study is published and preserved in [field-studies.md](field-studies.md). The five further reference questions now have complete numerical cases and reviewed publications. Sensitivity editions, original-source numerical reproductions and the remaining portable-report checks are still required; the existence of a protocol or completed reference does not close those gates.

| Question | Reference cases | Sensitivity cases | Main distinction |
|---|---:|---:|---|
| [Recovery packages](studies/field-recovery-v3.json) | 48 | 144 | Diagnosis only, fixed reset, human service, rover-assisted service |
| [Cleaning](studies/field-cleaning-v2.json) | 48 | 144 | No cleaning, periodic, condition dry, portable wet; clipping, feedstock and downstream limits |
| [Information](studies/field-information-v1.json) | 36 | 108 | Process sensors, fixed reader, rover; shared action options and bounded sensor failure |
| [Support](studies/field-support-v1.json) | 42 | 126 | Recovery/replenishment/remote/visit policies under support failures and shortages |
| [Provision and period costs](studies/field-provision-v1.json) | 36 | 108 | Owned/shared/contracted resident machinery versus a different on-call package |
| [Prepared inspection access](studies/field-interface-v1.json) | 24 | 72 | Same rover and process; enclosed contact versus accessible test port |

Reference cases span 72 hours, three fixed seeds and each declared condition. Sensitivities span 120 hours across the reference plant, a longer crew response and half-sized solar/electrolyser capacities. All remaining capacities and inventories stay absolute. An active explicit solar design retains geometry while its section ratings and converter are scaled together. Conditions are not pooled; differences and missing values have their own pair counts.

The cleaning fixture deliberately starts dirty and accumulates material quickly enough to exercise intervention in three days. It cannot recommend a real-world cleaning frequency. The support fixture executes scheduled routine work and standby electricity, with real finite crew and materials, but credits no unimplemented failure-prevention effect. The provision question explicitly assumes the same availability for owned/shared/contracted resident hardware and does not invent another site's contention. Its on-call arm changes equipment and labour as a package. Procurement at the study origin is distinct from allocated period cost and is not a recurrent purchase charge in a continuation.

The interface question covers a prepared inspection contact only. It does not complete the robot-compatible replaceable module or maintenance manipulator families. Those retain their required staged mechanical procedures, prerequisites and separate comparative study in stage 5.

Every publication must retain unsuccessful/incomplete attempts, actual service resources, ending inventories and backlog; publish an authored account of question, assumptions, results, limitations and implications; and verify saved-source reproduction. Read the original report and its source identity rather than treating later documentation as evidence about an older run.

After these comparisons, review which constraints actually explain the outcomes before implementing the joint service/production supervisor. A result favoring a simpler fixed sensor or human procedure is useful evidence, not a reason to remove the agreed hardware families from scope.

## Reviewed reference publications

These 186 cases span 72 hours each and passed 2,438,298 independent recorded checks. They are bounded numerical workflow evidence, not empirical calibration. Each report retains negative results, unresolved work and the applicable frozen assumptions.

| Question | Cases | Matched comparisons | Publication |
|---|---:|---:|---|
| cleaning | 48 | 36 | [Reviewed write-up](../runs/studies/8fb943d5926a4bdba20ade0fb34359d1/reports/edbf04db9b594b4d8e553633ec4ca39d.html) |
| information | 36 | 24 | [Reviewed write-up](../runs/studies/b872b8fc30904efbb508a996a8a3ea2e/reports/779c37aadb5d4357a79d49b3852e49e3.html) |
| support | 42 | 21 | [Reviewed write-up](../runs/studies/6cf7538d5009421ba80aa146962271f3/reports/2901829ae7a3478696614c6fc2a98675.html) |
| provision | 36 | 27 | [Reviewed write-up](../runs/studies/a2b2ba59cbd04b9f8f7520d570663e19/reports/301acd980493418280446173e430e4b3.html) |
| interface | 24 | 12 | [Reviewed write-up](../runs/studies/6b073b3ccf764798b374e7e4b627b171/reports/4576c06c815e4cf4b2bce65b680a02d8.html) |

The reporting correction is versioned separately from numerical execution: `field-study-reporting/2` counts ended restoration procedures that remain awaiting operating verification. It changes 114 case counts and no other outcome in these references. Earlier publications and physical traces remain immutable. The new derivation source is preserved with the report. The first cleaning bundle passed standalone integrity and independent checks for all 48 cases; the revised bundles and numerical reruns remain separate work.

## Reproduction progress

The cleaning and information references have now been numerically reproduced from their original `d98bf755…` source. All 48 cleaning cases and 36 information cases retain the same interval counts, applied actions and methane totals, and their independent checks pass. The revised reviewed publications also passed offline bundle checks for all 84 archives. These are separate results: numerical rerun agreement does not follow merely from being able to open a saved report.

Detailed comparisons are saved in `build/services/local-policy/checked/cleaning-original-source-reproduction-review.json` and `information-original-source-reproduction-review.json`. The original-source rerun editions are `3f11519a21ca473a882e56c4492f1e20` and `3098cc10b053403b93ff673ee9d489f0`; revised portable-export identities are in `reviewed-export-results.json`. Remaining reference reruns, exports and all six sensitivity editions continue from frozen sources. This does not yet close stage 3.

Current field protocol revisions explicitly record `legacy-reason/1` outcome matching. The new optional [event matching model](service-outcome-matching.md) requires a declared shared basis change. These active historical-source reruns and sensitivities keep their original assumptions.

The support reproduction and revised portable bundle subsequently completed all 42 cases. Across cleaning, information and support, all 126 original-source reruns match their complete service records, retrospective states and metrics, in addition to their applied plant actions. Their source identities, weather and independent checks match. The detailed comparison is `build/services/local-policy/checked/reproduced-service-trace-review.json`. The support rerun edition is `60e5abb7c04346cbab637722912b4c10`, with report `a1d266672b13470d9b6c102b27adf30b`. Provision/interface reruns, their exports and the sensitivity programme remain separate work.

The provision rerun and revised offline bundle also passed all 36 cases. All 162 cases across the first four questions have identical service and retrospective traces and metrics. The provision comparison is included in `reproduced-service-trace-review.json`; its rerun edition is `cabdcd5ef69b4451992e7987f05d5fd8` and report `106c9754b9a246b7b0f8bb914d126c4b`. Interface and sensitivity completion must be checked separately.
