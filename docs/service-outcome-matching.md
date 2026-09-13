# Matching service outcomes across controllers

`target-action-request/1` is an optional execution model, selected in Field operations setup under **Service outcome matching**. It is a prerequisite for joint service/production comparisons, not a service planner. All probabilities remain illustrative inputs; this mechanism does not establish real hardware reliability.

## What is matched

Each accepted work request receives a stable event identity: target asset identifier, action, and a positive request number counted separately for that target/action pair. The seed and outcome channel complete the key. Registration occurs after resource reservations and acceptance, including jobs accepted in a combined crew visit. Candidate construction and rejected dispatch do not consume a number. An accepted job that is later cancelled retains its number.

This makes a matched draw independent of human-readable explanations, order identifiers, assigned actor, scheduled hour, unrelated tasks and the order in which outcome channels are evaluated. It deliberately does not equate different actions or later accepted requests. A policy that attempts the same action twice uses requests 1 and 2 even if another policy attempts it only once. No hidden injected-incident label is needed to match an event.

The same uniform variate can yield different outcomes when probabilities, compatibility or operating conditions differ. Matching randomness does not force the same physical trace and does not make a comparison fair when other environmental assumptions differ. Field Studies require the matching model to be the same across all arms of a matched group.

## Exact calculation and information boundary

Encode `["target-action-request/1", seed, target, action, request_number, channel]` as UTF-8 JSON with ASCII escaping and comma/colon separators, without spaces. Take SHA-256, retain its first 53 bits as an unsigned integer, and divide by 2⁵³. The result is an exactly representable binary fraction in [0, 1). An assumed Bernoulli success occurs when that fraction is strictly below the applicable success probability; a mission abort instead compares against its failure probability.

For seed 7, target `PLANT-01/ELY-01`, action `module-replacement`, request 1 and channel `repair`, the numerator is 8,984,797,099,206,352 and the fraction is 0.9975128611124209. Request 2 produces numerator 1,514,810,012,951,362 and fraction 0.16817769543113337. These are algorithm test vectors, not observed plant probabilities.

Public order and planned-mission records contain the event identity. Uniform draws and core procedure outcomes are recorded only in `retrospective_truth_by_controller`; the service supervisor receives observations and resource state. Repeated use of a channel returns its one cached draw. The private ledger records its first execution interval once, so replay can distinguish when it was evaluated from when work completed or an observation became available.

This covers the service executive's mission failures, ideal-contact read errors/unavailability, repair procedures and supervised drive-test channels. The referenced contact reader retains its separate `referenced-contact/1` reader/time/channel noise model. Observation and outcome models are identified separately; neither can be inferred from an animation.

## Compatibility and checking

The default remains `legacy-reason/1`, which preserves the original SHA-256 mapping over seed/action/reason/channel. Missing fields in old configurations restore that compatibility mode. New field protocol revisions explicitly state it; prior protocol files, archived attempts, publications and frozen-source numerical reruns are not rewritten. Choosing the new mapping produces `plant-service-contracts/10` records and a manifest explaining its scope. This version does not change the underlying mission-plan or crew-visit schemas.

The independent checker reconstructs accepted request ordinals and exact fractions using a separate hexadecimal/decimal calculation. It verifies private recording, identity consistency, one draw per channel and the applicable core repair, hardware-procedure and supervised-test outcomes. Tests include fixed algorithm vectors, rejected candidates, combined visits, partial failure, retrieval, compatibility, changed future faults and forged records. Internal consistency is distinct from empirical validation of the assumed probabilities.

The original plant illustrations are unchanged. Learning examples, full service essays, service planning and the remaining hardware/degradation programme remain separately required by the [roadmap](field-operations-roadmap.md).

## Saved verification examples

Run `.venv/bin/python -m methane.services.randomness_demo` for three independent constant-irradiance fixtures. The saved [example report](../build/services/matching/report.md) links playback, while `cases.json` records fixture identity, exact source, private draws and ending states. The initial source `492d03e811ff253862fcc3ea5f31fa434696c5082b031da16e945d8c0ea9b7e5` passed 3,124 independent checks for crew repair, 4,640 for partial cleaning/retrieval and 4,554 for hardware replacement. The three original-source bundles passed standalone offline checking and numerical rerun with zero applied-action, methane or cost differences. See `build/services/matching/restoration-checks.json` for the separate checks and original identities.

These 12,318 checks reconcile declared model behaviour. They do not establish empirical probabilities, a robot-versus-human ranking or a complete planning policy. The full Python regression suite for that source passed 459 tests and the Node suite passed 58 tests; test and example source identities remain separate from any later release.
