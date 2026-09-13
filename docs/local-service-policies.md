# Explicit local cleaning and contact access

This increment adds `local-cleaning-policy/1` and `contact-access/1` to opt-in `plant-service-contracts/9`. Earlier implementations and archived decisions remain available. The default `legacy-condition` rule and `legacy-prepared` contact retain their previous behavior.

## Cleaning rules

The explicit rules share section-optical execution, tools, resource reservations and effect timing. They do not get future weather, process-fault identity or successful-repair truth.

- **Off:** no new cleaning requests. Installed equipment and its standing costs still exist.
- **Condition:** use the declared ideal surface monitor. Choose the section with the greatest compatible treatable loss among sections above its treatment threshold. Dry brushing treats loose dirt; compatible wet brushing also treats its configured adhered fraction. This is an ideal monitoring assumption, not a claim that the robot has a dirt camera.
- **Periodic:** start from an editable first-due hour and select the oldest due section, with identifier as a deterministic tie-break. The next due hour is actual full-pass work completion plus the recurrence. This is a completion-based recurrence, not a fixed calendar appointment. It does not infer a benefit from dirt level or electricity price.

A partial pass consumes actual resources and changes its covered optical surface. It earns no completed-pass recurrence credit. A fully completed pass retains its credit if the subsequent return fails; the robot's failed return and need for recovery still remain. Scarce stock leaves a visible queued request; it is not hidden until a kit appears. At most one outstanding task per cleaning method is queued, and the local rules exclude sections already occupied by another cleaning method. All shared travel, crew and equipment reservations still apply.

The local rules do not jointly plan future robot charging, inspect predicted rain or optimize production. These remain stage 4 work.

## Contact access

An accessible port adds a known compatibility requirement to `ELY/contact`. An enclosed contact fails that requirement for the installed fixed/mobile contact-reader payload. Direct task construction checks the requirement as well as the local policy; changing only a rendered label cannot enable a read.

The local diagnosis policy skips a known incompatible contact read and requests its compatible qualified-human alternative. That procedure remains investigative module substitution rather than an asserted fault diagnosis. An accessible port permits measurement; zero/span references, delay, error, uncertainty, action permission and subsequent operating verification continue to apply. Nothing in this model permits arbitrary visual diagnosis or robotic module replacement.

The interface-study's illustrative €1,500 prepared-port fitout is recorded as rover access infrastructure. Both designs retain the same rover, tools, process faults and human fallback. This is an inspection-interface comparison, not completion of the stage 5 replaceable-module/manipulator work.

## Recorded outcomes and preservation

`field-period-outcomes/1` adds period area, full passes, water, converter clipping, usable referenced-contact decision hours, first usable contact hour, unserved dock controls and routine procedure counts. A mechanism that was not recorded remains undefined. First usable hour is an absolute decision hour from run origin, not a detection delay; multiple hours can contain the same still-valid sample. The independent standard-library checker totals these fields and reconstructs cadence from phase events.

New study protocols select question-specific outcome tables. Python calculates all differences, means, ranges and available-pair counts; browser and offline reports render those saved values. Old publications and archives are not rewritten. New restoration backlog metrics count ended reset/replacement/calibration tasks requiring acceptance; old result summaries keep their recorded original scope.

`field-study-reporting/2` corrects a derived count which previously missed the fractional executive's `awaiting verification` state. A new-contract restoration procedure counts when it has a recorded mission completion time, remains completed or awaiting verification, and has no recorded acceptance. Failed, cancelled, active, inspection, cleaning and routine orders do not count. This is completion of an attempted procedure, not proof of physical restoration. Older summaries without period outcomes retain their legacy completed-status count; no missing original telemetry is invented.

New publications identify their reporting implementation and source separately from the original numerical execution. Each study preserves the reporting source capsule once per identity, including it in reproduction bundles. Reading a publication checks that source; an absent original source is reported missing rather than reconstructed. Revised tables are new publications over the same immutable attempts. The Protocol and assumptions view exposes these identities and metric definitions.

The named solar study transform supports an explicit capacity factor (including every section and converter of an existing design) and a converter-to-array fraction. Orientation and shading remain intact. A missing explicit design can be instantiated from the documented three-section default only when the protocol expressly requests a converter comparison. Every resolved value is saved. Unknown transforms and invalid operands are rejected.

## Remaining gates

Mechanism acceptance includes unavailable inputs, independent full-pass clocks, partial failures, direct incompatible-build rejection, prior-information preservation and forged-record detection. Comparative conclusions require actual published editions, not the existence of a protocol. Full service essays, joint planning, remaining hardware and learned policies remain required by the six-stage roadmap.
