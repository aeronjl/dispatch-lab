# Reactor verification boundary

TLC checks all reachable states for minimum-run durations 1–4 in a finite
abstraction. `beginningSafe` and `endingSafe` represent the production temperature
band; `resources` represents feasible feedstock/electrical dispatch. Failure
represents an execution failure. Environment inputs are nondeterministic.

The controller requests production; an existing commitment also requests
continuation. Applied production requires both temperature bounds, resources and
successful execution. An interrupted request/commitment is an explicit trip.
Heating and cooling labels describe a non-producing interval.

This is not a proof of continuous physics, Python floating-point arithmetic,
solver optimality, eventual recovery, or real-plant fidelity. Thermal reference
and Python conformance tests supply separate evidence. No liveness claim assumes
that weather or equipment will eventually recover.

Run `python -m methane.engineering formal --java /path/to/java --jar /path/to/tla2tools.jar`.
Use TLC 1.7.4 (checksum enforced by the runner); Java 17 is used in CI.
Reports include source/tool hashes, invocation, state counts and full checker output.
