# Completed v0.2 evidence

**51 experiments / 153 controller traces** completed: 18 synthetic cases, 18 diagnosis-disabled ablations, six thermal sensitivities and nine ten-day historical windows. All three policies ran in each case. The suite-wide maximum recorded conservation residual was 8.53 × 10⁻¹⁴ (in the respective balance units).

The reports preserve two early assertion failures as previous attempts and 12 superseded probe-policy attempts. The failed cases completed after physical replay validation was added. Affected probe cases were rerun after keeping Greedy probes local and preventing first-interval methane from relying on unconfirmed extra hydrogen production.

| Observation | Evidence | Interpretation |
|---|---|---|
| Methane MPC can help | More methane than Greedy in 7 of 18 synthetic cases | Planning is useful under particular energy, material and thermal constraints; it is not an automatic improvement |
| Objective choice matters | Economic MPC improved the defined variable-input-and-wear contribution in all 18 synthetic cases | Applies to this illustrative price/cost fixture, with no terminal inventory sale value; it is not investment return |
| Stored hydrogen alone is insufficient | Normal seed 42: Greedy 330.0 kg CH₄, methane MPC 379.3 kg | Greedy ends with 58.8 kg H₂ but an empty battery and a 139.6°C reactor. MPC ends with 26.8 kg H₂, 391.7 kWh and 264.1°C |
| Period output needs ending inventories | Normal seed 7: Greedy 398.5 kg, methane MPC 382.1 kg | MPC ends with 372.2 kWh versus 29.5 kWh and more H₂. Lower period output alone does not establish a worse continuing operating position |
| Feedstock imposes a ceiling | Standard 72-hour supply: 1,100 kg CO₂; delayed schedule: 800 kg | Ideal stoichiometry limits methane to 400.0 kg and 290.9 kg respectively, before electrical or thermal losses constrain it further |
| Diagnosis requires excitation | Capacity loss and flow bias can be confirmed after two informative intervals; some capacity-loss cases remain unconfirmed | Lack of tracking evidence is retained as uncertainty rather than treated as health |

There were zero **confirmed-incident false alarms** in the completed suite. This metric does not mean every estimate was certain: ambiguous balance observations can cause conservative derating, and uncertainty hours are reported separately. Flow-channel isolation protects usable-flow telemetry; dispatch already has independent tank inventory. Flow-sensor ablation therefore need not change physical dispatch. Do not attribute every output difference to diagnosis when time-limited solver incumbents also differ.

Many MPC decisions reached their 0.5-second solver limit. The reports show limited solutions and fallbacks alongside physical/economic outcomes. These experiments establish inspectable examples and counterexamples, not proof of controller optimality or calibrated industrial performance.

Full local reports and machine-readable records:

- [Synthetic cases](../runs/methane-v2/batches/report-synthetic.md)
- [Diagnosis ablation](../runs/methane-v2/batches/report-ablation.md)
- [Thermal sensitivities](../runs/methane-v2/batches/report-thermal.md)
- [Historical windows](../runs/methane-v2/batches/report-historical.md)
- [All case metrics and archive references](../runs/methane-v2/batches/evidence-all.json)

Raw weather, decisions and traces are stored locally under `runs/`, outside Git. Use the batch runner to reproduce the reports; each case links to its saved archive. See [model assumptions](methane-model.md) and the [guided demonstration](guided-demo.md).
