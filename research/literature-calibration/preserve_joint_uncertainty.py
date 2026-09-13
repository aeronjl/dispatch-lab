"""Preserve previously specified whole-day bootstrap draws without changing the report.

This produces a new, explicitly conditional reference ensemble. It does not
adopt SUPSI module parameters as a calibration of the illustrative plant.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from analyse import fit_faiman

root = Path(__file__).resolve().parent
source = root / "analysis/pv-predictions.csv"
data = pd.read_csv(source, parse_dates=["datetime"])
data = data[data["split"] == "training"]
g = data.Gpoa.to_numpy()
w = data.WIND_SPEED.to_numpy()
rise = (data.Tbom - data.AIR_TEMP).to_numpy()
days, indices = np.unique(data.datetime.dt.date, return_inverse=True)
rng = np.random.default_rng(20260912)
rows = []
for _ in range(80):
    counts = np.bincount(rng.integers(0, len(days), len(days)), minlength=len(days))
    weights = counts[indices]
    p = fit_faiman(g, w, rise, weights)
    noct = 20 + 800 * np.sum(weights * g * rise) / np.sum(weights * g * g)
    rows.append([float(p[0]), float(p[1]), float(noct)])
result = {
    "schema_version": "dispatch-lab/reference-ensemble/1",
    "id": "supsi-odd-month-day-bootstrap/1",
    "parameters": ["Faiman U0", "Faiman U1", "effective NOCT"],
    "units": ["W/(m² K)", "W s/(m³ K)", "°C"],
    "rows": rows,
    "seed": 20260912,
    "method": "80 resamples of complete training days; three fitted values retained together per replicate",
    "source": "SUPSI IEA-PVPS Task 13 Annex 1, existing cached dataset",
    "source_artifact": "research/literature-calibration/analysis/pv-predictions.csv",
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "training_days": len(days),
    "training_rows": len(data),
    "support": "Same site, module, selected daylight observations and alternating-month training split as the original report.",
    "excluded_uncertainty": [
        "Systematic measurement errors",
        "New site or module transfer",
        "Weather forecast error",
        "Model discrepancy",
    ],
    "application": "Reference ensemble only. Faiman coefficients are not implemented production inputs. Effective NOCT can be tested only as an explicitly scoped disclosed scenario; no automatic transfer to the plant.",
    "dependence": "Joint rows must be preserved; NOCT and Faiman are alternative descriptions of the same data, not simultaneous independent heat-loss mechanisms.",
}
output = Path("docs/uncertainty/supsi-reference-ensemble-v1.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
print(output, len(rows), "joint rows")
