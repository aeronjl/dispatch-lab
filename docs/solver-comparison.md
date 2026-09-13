# Controlled battery solver comparison

All solves use one recorded state, forecast and cost basis. Bounds apply to the same minimization objective, including tie-breaks. A longer budget is a reference attempt, not an optimality guarantee. Whole-run differences also compound changed subsequent state.

Recorded decision: `bed1bc466dac58c0` / MPC · methane / interval 7. Linear formulations equivalent within 1e-12: **True**.

| Formulation | Budget s | Status | Objective | Bound | Gap | Predicted methane kg | Independent physics |
|---|---:|---|---:|---:|---:|---:|---|
| affine/1 | 0.5 | time-limited | -173.8236040708704 | -174.7666966725671 | 0.00542557270479893 | 173.97906645785105 | True |
| loss-ledger/1 | 0.5 | time-limited | -173.82438805743877 | -175.564218330142 | 0.010009126407097332 | 173.97985236023183 | True |
| affine/1 | 5.0 | solved | -173.8236040708704 | -173.9175201737687 | 0.0005402954529697483 | 173.97906645785105 | True |
| loss-ledger/1 | 5.0 | solved | -173.82438805743877 | -173.9945292429161 | 0.0009788107835656417 | 173.97985236023183 | True |
| affine/1 | 20.0 | solved | -173.8236040708704 | -173.9175201737687 | 0.0005402954529697483 | 173.97906645785105 | True |
| loss-ledger/1 | 20.0 | solved | -173.82438805743877 | -173.9945292429161 | 0.0009788107835656417 | 173.97985236023183 | True |

The original runs first requested different actions at interval 7. At the selected interval their estimates match: True; forecasts match: True. Their whole-run methane totals were [234.78900319045306, 207.70098712173126] kg. Original solver details and all controlled actions are retained in the JSON report.

Positive row scaling leaves the mathematical feasible set unchanged. Solver branch/search paths and wall-clock cutoffs can change the incumbent. Different applied actions then change subsequent inventories and later decisions. Comparing later whole-run states is not a controlled test of component physics.

This report measures the observed effects; it does not assume that longer solves always improve a single stochastic wall-clock run or certify an optimum without a matching bound.
