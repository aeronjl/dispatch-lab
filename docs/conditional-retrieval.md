# Charging after an observed stranding

`conditional-retrieval-charging/1` extends coordinated dock planning with a
bounded continuation. An already observed stranded robot can receive a future
charging allocation after a nominated, qualified retrieval completes. Every
stranded origin must be covered. The registered crew, recovery carrier, route,
time, energy, stock and prices remain in the combined resource projection.

The earliest charging boundary is the first hourly boundary at or after the
**whole retrieval mission**, including crew return. A combined visit waits for
its last member. Returning a robot is not a consumable delivery: its price uses
the retrieval activity quantities without inventing a destination stock capacity.
Other replenishment acceptance limits remain unchanged.

The candidate labels this conditional return explicitly. It grants neither
repair success nor readiness for another mission. Execution still requires the
actual retrieval and the existing separate drive check. No missing crew, future
repair, unobserved fault or new hardware capability is created by the planner.
Hypothetical interruptions in future uncertainty branches retain their existing
conservative charging restrictions; this is not a full contingent fleet policy.

`tests/test_retrieval_planning.py` restores an actual recorded stranding and its
original planning information. It checks feasible later charging, rejection of
premature charging and omitted retrieval, source immutability, and an independent
standard-library check of receipt/mission boundaries. The archive checker uses
the same saved operands, not production-planner results as its expected answer.
