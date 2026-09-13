"""Offline reference calibration. Never imports or modifies production configuration."""

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "analysis"


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def scores(observed, predicted):
    error = predicted - observed
    return dict(
        n=len(error),
        rmse=float(np.sqrt(np.mean(error**2))),
        bias=float(np.mean(error)),
        mae=float(np.mean(abs(error))),
    )


def fit_faiman(g, wind, rise, weights=None):
    weights = np.ones(len(g)) if weights is None else np.sqrt(weights)

    def residual(p):
        return (g / (p[0] + p[1] * wind) - rise) * weights

    def jacobian(p):
        common = -g / (p[0] + p[1] * wind) ** 2 * weights
        return np.column_stack((common, common * wind))

    result = least_squares(residual, [30, 3.4], jac=jacobian, bounds=([1, 0], [100, 50]))
    assert result.success
    return result.x


def pv():
    frames = []
    for path in sorted(RAW.glob("supsi-*.csv")):
        frame = pd.read_csv(path, sep=";")
        frame.columns = frame.columns.str.strip()
        for column in ["Gpoa", "AIR_TEMP", "Tbom", "WIND_SPEED", "Pm"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["datetime"] = pd.to_datetime(
            frame.Date.str.strip() + " " + frame.Time.str.strip(), format="%d.%m.%Y %H:%M:%S"
        )
        frame["source_file"] = path.name
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True).sort_values("datetime")
    assert data.datetime.nunique() == len(data)
    good = (
        np.isfinite(data[["Gpoa", "AIR_TEMP", "Tbom", "WIND_SPEED"]]).all(axis=1)
        & (data.Gpoa >= 200)
        & (data.WIND_SPEED >= 0)
    )
    valid = data[good].copy()
    g, w, ambient, temp = (valid[c].to_numpy() for c in ["Gpoa", "WIND_SPEED", "AIR_TEMP", "Tbom"])
    train = valid.datetime.dt.month.to_numpy() % 2 == 1
    rise = temp - ambient
    slope = np.dot(g[train], rise[train]) / np.dot(g[train], g[train])
    coefficients = fit_faiman(g[train], w[train], rise[train])
    predictions = {
        "NOCT45": ambient + g * 25 / 800,
        "fitted_NOCT": ambient + g * slope,
        "published_Faiman": ambient + g / (29.84 + 3.44 * w),
        "fitted_Faiman": ambient + g / (coefficients[0] + coefficients[1] * w),
    }
    # Resample whole days. This captures sampling variability, not sensor bias or site transfer.
    days, day_index = np.unique(valid.loc[train, "datetime"].dt.date, return_inverse=True)
    rng = np.random.default_rng(20260912)
    boot = []
    for _ in range(80):
        count = np.bincount(rng.integers(0, len(days), len(days)), minlength=len(days))
        weights = count[day_index]
        p = fit_faiman(g[train], w[train], rise[train], weights)
        n = 20 + 800 * np.sum(weights * g[train] * rise[train]) / np.sum(weights * g[train] ** 2)
        boot.append([*p, n])
    rows = []
    for label, mask in [("training_odd_months", train), ("holdout_even_months", ~train)]:
        for model, pred in predictions.items():
            rows.append(dict(split=label, model=model, **scores(temp[mask], pred[mask])))
    monthly = []
    for month in range(1, 13):
        mask = valid.datetime.dt.month.to_numpy() == month
        for model, pred in predictions.items():
            monthly.append(
                dict(
                    month=month,
                    split="train" if month % 2 else "holdout",
                    model=model,
                    **scores(temp[mask], pred[mask]),
                )
            )
    valid["split"] = np.where(train, "training", "holdout")
    for label, pred in predictions.items():
        valid[label] = pred
    valid.to_csv(OUT / "pv-predictions.csv", index=False)
    # Separate electrical check using measured module temperature and independent lab parameters.
    electrical = np.isfinite(valid.Pm) & (valid.Pm > 0)
    predicted_w = 285.68591743441357 * g / 1000 * (1 - 0.00405 * (temp - 25))
    electrical_scores = scores(valid.loc[electrical, "Pm"].to_numpy(), predicted_w[electrical])
    result = dict(
        source="SUPSI IEA-PVPS Task13 Annex1",
        raw_rows=len(data),
        accepted_rows=len(valid),
        excluded_rows=int((~good).sum()),
        months=sorted(data.datetime.dt.month.unique().tolist()),
        units="Temperature errors K; module power W",
        training_days=len(days),
        parameters=dict(
            U0=float(coefficients[0]),
            U1=float(coefficients[1]),
            effective_NOCT=float(20 + 800 * slope),
        ),
        bootstrap_95_percentiles=dict(
            zip(
                ["U0", "U1", "effective_NOCT"],
                np.percentile(boot, [2.5, 97.5], axis=0).T.tolist(),
                strict=True,
            )
        ),
        bootstrap_replicates=80,
        scores=rows,
        monthly=monthly,
        electrical_measured_temperature_check=electrical_scores,
        caveats=[
            "Back-of-module temperature, not cell junction temperature.",
            "Alternating-month hold-out at the same site and module. No external-site validation.",
            "Odd-month calibration includes January. January is not an independent transfer test in this split.",
            "No filtering by residuals or output accuracy. Dataset already contains selected daylight records; not an annual energy-yield measurement.",
            "Time labels retained as supplied without claiming UTC: the supplied CSV header does not specify timezone.",
            "Bootstrap intervals exclude systematic metrology and transfer uncertainty.",
        ],
    )
    # Explicit seasonal transfer: July-only fit, January-only test, separate from main split.
    july = valid.datetime.dt.month.to_numpy() == 7
    jan = valid.datetime.dt.month.to_numpy() == 1
    july_coef = fit_faiman(g[july], w[july], rise[july])
    result["july_to_january"] = dict(
        coefficients=july_coef.tolist(),
        **scores(temp[jan], ambient[jan] + g[jan] / (july_coef[0] + july_coef[1] * w[jan])),
    )
    save("pv.json", result)


def pem():
    names = [
        "power_command",
        "stack_power",
        "smps_power",
        "subsystem_power",
        "chiller_power",
        "hydrogen_flow",
        "hydrogen_flow_cs",
    ]
    data = pd.DataFrame(
        {name: np.loadtxt(RAW / f"pem-data__experiment__{name}.txt") for name in names}
    )
    data["time"] = pd.to_datetime(
        (RAW / "pem-data__experiment__timestamp.txt").read_text().splitlines(),
        format="%d-%b-%Y %H:%M:%S",
    )
    assert len(data) == 15068 and (data.time.diff().dropna().dt.total_seconds() == 1).all()
    data["system_power"] = data.smps_power + data.subsystem_power + data.chiller_power
    groups = (data.power_command.diff().fillna(0) != 0).cumsum()
    segments = []
    for i, segment in data.groupby(groups):
        if len(segment) < 900 or segment.power_command.iloc[0] <= 0:
            continue
        stable = segment.iloc[120:].copy()
        boundary = len(stable) // 2
        for split, sub in [
            ("training", stable.iloc[:boundary]),
            ("holdout", stable.iloc[boundary:]),
        ]:
            segments.append(
                dict(
                    segment=int(i),
                    split=split,
                    n=len(sub),
                    start=str(sub.time.iloc[0]),
                    end=str(sub.time.iloc[-1]),
                    **{c: float(sub[c].mean()) for c in names + ["system_power"]},
                )
            )
    means = pd.DataFrame(segments)
    means.to_csv(OUT / "pem-plateaus.csv", index=False)
    models = []
    for power in ["stack_power", "system_power"]:
        for channel in ["hydrogen_flow", "hydrogen_flow_cs"]:
            train = means.split == "training"
            test = ~train
            x, y = means.loc[train, power].to_numpy(), means.loc[train, channel].to_numpy()
            slope = float(x @ y / (x @ x))
            affine = np.linalg.lstsq(np.column_stack((x, np.ones(len(x)))), y, rcond=None)[0]
            xx, yy = means.loc[test, power].to_numpy(), means.loc[test, channel].to_numpy()
            for name, pred in [
                ("constant_55", xx / 55),
                ("fitted_constant", xx * slope),
                ("fitted_affine", xx * affine[0] + affine[1]),
            ]:
                models.append(
                    dict(
                        power_boundary=power,
                        hydrogen_channel=channel,
                        model=name,
                        **scores(yy, pred),
                    )
                )
            models.append(
                dict(
                    power_boundary=power,
                    hydrogen_channel=channel,
                    model="parameters",
                    fitted_kwh_per_kg=1 / slope,
                    affine_kg_per_kwh=float(affine[0]),
                    affine_kg_per_h=float(affine[1]),
                )
            )
    rows = []
    for _, row in means[means.split == "holdout"].iterrows():
        rows.append(
            dict(
                command_kw=row.power_command,
                stack_kw=row.stack_power,
                system_kw=row.system_power,
                flow_channel_kgph=row.hydrogen_flow,
                cs_channel_kgph=row.hydrogen_flow_cs,
                stack_specific_measured_channel=row.stack_power / row.hydrogen_flow,
                system_specific_measured_channel=row.system_power / row.hydrogen_flow,
                channel_difference=row.hydrogen_flow_cs - row.hydrogen_flow,
            )
        )
    # Freeze authors' tabulated characterization separately from our raw-data fit.
    author = dict(
        stack_kw=[15.6, 20.8, 26, 31.2, 36.4, 41.6, 46.8, 52],
        system_kw=[36.4, 41.8, 47.3, 52.9, 58.4, 63.9, 69.4, 74.9],
        gross_kgph=[0.32, 0.40, 0.49, 0.58, 0.66, 0.73, 0.82, 0.89],
        net_kgph=[0.20, 0.28, 0.37, 0.46, 0.54, 0.61, 0.70, 0.77],
    )
    for name, key in [("gross_stack", "stack_kw"), ("net_system", "system_kw")]:
        flow = author["gross_kgph" if name == "gross_stack" else "net_kgph"]
        author[name + "_kwh_per_kg"] = (np.array(author[key]) / flow).tolist()
    save(
        "pem.json",
        dict(
            samples=len(data),
            retained_plateaus=len(rows),
            units="Power kW; flow kg/h; errors kg/h",
            scores=models,
            holdout_plateaus=rows,
            authors_characterization=author,
            caveats=[
                "Experimental source is a recently published dataset with a July2026 preprint; peer-reviewed publication was not verified.",
                "Eight long 30-minute plateaus; 120-second settling omitted then first/second halves separated. Short commissioning/startup plateaus excluded by a prespecified clarification before coefficient fitting.",
                "Hydrogen channel names are preserved. Authors' published gross/net mapping is not assumed to prove two independent calibrated flow sensors.",
                "Same-day plateau validation is internal repeatability; not independent equipment validation.",
                "System power includes AC/DC supply plus chiller and subsystem channels; stack boundary is DC. Neither is directly interchangeable with the present plant bus without an explicit boundary adapter.",
                "Authors' 0.12kg/h purification allowance is tabulated separately, not labelled a fitted purge measurement.",
                "A pointwise fit does not establish startup energy, lifetime degradation or fault incidence.",
            ],
        ),
    )


def density_z(p_mpa, t_k):
    if not (150 <= t_k <= 1000 and 0 <= p_mpa <= 200):
        raise ValueError("Outside published density correlation domain")
    a = np.array(
        [
            0.05888460,
            -0.06136111,
            -0.002650473,
            0.002731125,
            0.001802374,
            -0.001150707,
            0.00009588528,
            -0.0000001109040,
            0.0000000001264403,
        ]
    )
    b = np.array([1.325, 1.87, 2.5, 2.8, 2.938, 3.14, 3.37, 3.75, 4])
    c = np.array([1, 1, 2, 2, 2.42, 2.63, 3, 4, 5])
    return float(1 + np.sum(a * (100 / t_k) ** b * p_mpa**c))


def reference_calculations():
    checks = []
    for t, p, z, rho in [
        (200, 1, 1.00675450, 0.59732645),
        (300, 10, 1.05985282, 3.78267048),
        (400, 50, 1.24304763, 12.09449023),
        (500, 200, 1.74461629, 27.57562673),
        (200, 200, 2.85953449, 42.06006952),
    ]:
        actual = density_z(p, t)
        density = p * 1000 / (actual * 8.314472 * t)
        assert abs(actual - z) < 1e-8 and abs(density - rho) < 1e-8
        checks.append(
            dict(
                temperature_k=t,
                pressure_mpa=p,
                z=actual,
                reference_z=z,
                molar_density_mol_per_l=density,
                reference_molar_density=rho,
            )
        )
    storage = []
    for pressure_bar in [20, 30, 100, 200, 350]:
        z = density_z(pressure_bar / 10, 293.15)
        rho = pressure_bar * 1e5 * 0.00201588 / (z * 8.314472 * 293.15)
        storage.append(
            dict(
                pressure_bar=pressure_bar,
                z=z,
                density_kg_per_m3=rho,
                volume_for_60kg_m3=60 / rho,
                ideal_gas_density_overstatement_percent=(z - 1) * 100,
            )
        )
    save(
        "gas.json",
        dict(
            reference_checks=checks,
            storage_examples=storage,
            scope="Density correlation only; no pressure-vessel design or safety certification. Pressure selection is a design assumption.",
        ),
    )
    # Published coefficients; no new fitting and no unprovided covariance reconstructed.
    coefs = [
        [101.1, 0.03028, -4.493],
        [97.81, 0.02736, -3.065],
        [97.30, 0.02692, -3.379],
        [97.72, 0.03237, -5.629],
    ]
    battery = []
    for year, (a, b, c) in enumerate(coefs, 1):
        for p in [0.15, 0.32, 0.55, 1] if year < 4 else [0.1, 0.15, 0.32, 0.55, 1]:
            efficiency = (a * p / (b + p) + c * p) / 100
            assert 0 < efficiency < 1
            battery.append(
                dict(year=year, power_pu=p, power_kw=p * 500, rte_without_separate_aux=efficiency)
            )
    save(
        "battery.json",
        dict(
            source="Grimaldi2023 table6",
            coefficients=coefs,
            curve=battery,
            boundary="500kW/822kWh NMC AC-coupled installation; operating energy657.6kWh. Separate auxiliaries must not be included twice.",
            evidence="Reproduction of authors' regression, not independent refit or validation; source raw SCADA unavailable here.",
        ),
    )


def reactor():
    digitized = json.loads((HERE / "reactor-digitization.json").read_text())
    xy = np.array(digitized["temperature_pixels"])
    t = (xy[:, 0] - 174) * 40 / (539 - 174)
    y = 260 + (358 - xy[:, 1]) * 80 / (358 - 134)

    def predicted(p):
        base, amplitude, tau = p
        return base + amplitude * (1 - np.exp(-np.maximum(t - 5, 0) / tau))

    def fit(obs):
        r = least_squares(
            lambda p: predicted(p) - obs, [320, 14, 8], bounds=([315, 5, 0.1], [325, 25, 50])
        )
        assert r.success
        return r.x

    p = fit(y)
    rng = np.random.default_rng(20260912)
    variants = np.array([fit(y + rng.uniform(-1, 1, len(y))) for _ in range(200)])
    pd.DataFrame(dict(time_minutes=t, temperature_c=y, fitted_c=predicted(p))).to_csv(
        OUT / "reactor-points.csv", index=False
    )
    save(
        "reactor.json",
        dict(
            baseline_c=float(p[0]),
            increment_k=float(p[1]),
            effective_time_constant_minutes=float(p[2]),
            digitization_perturbation_95_percentiles_minutes=np.percentile(
                variants[:, 2], [2.5, 97.5]
            ).tolist(),
            **scores(y, predicted(p)),
            scope="Effective response to a feed-rate step with coolant inlet held310C. Not ambient heat loss; does not identify independent C and UA. Perturbation interval is not an experimental confidence interval.",
            fit="First-order descriptive fit to manually digitized published figure8; fixed input step at5min; all points fit, no independent hold-out.",
        ),
    )


def main():
    from derived import calculate

    OUT.mkdir(exist_ok=True)
    pv()
    pem()
    reference_calculations()
    reactor()
    save("derived.json", calculate())
    outputs = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in OUT.iterdir()
        if p.suffix in {"csv", "json"} and p.name != "manifest.json"
    }
    save(
        "manifest.json",
        dict(
            schema_version="dispatch-lab/literature-analysis/1",
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
            analysis_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            inputs={
                str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [
                    HERE / "derived.py",
                    HERE / "protocol.json",
                    HERE / "protocol-clarification.json",
                    HERE / "reactor-digitization.json",
                    RAW / "reactor-slurry-page8.png",
                    *[
                        RAW / name
                        for name, record in json.loads(
                            (HERE / "downloads.json").read_text()
                        ).items()
                        if record["status"] == "downloaded"
                    ],
                ]
            },
            environment=dict(
                python=platform.python_version(),
                packages={
                    name: importlib.metadata.version(name) for name in ["numpy", "scipy", "pandas"]
                },
            ),
            outputs=outputs,
        ),
    )
    print(
        json.dumps(
            {
                name: json.loads((OUT / f"{name}.json").read_text())
                for name in ["pv", "pem", "gas", "reactor"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
