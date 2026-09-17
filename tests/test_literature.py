"""Reference-device checks are not validation of the configured plant."""

import hashlib
import json
import math
from copy import deepcopy

import pytest

from methane.literature import adapters, models, service
from methane.siting import equipment, reporting
from methane.siting.store import Store, digest


def test_source_reference_regression_and_independent_linear_fit():
    r = service.calculate({"profile": "csu-pem"})
    rows = [x for x in r["rows"] if x["split"] == "development"]
    x = [v["system_power"] for v in rows]
    y = [v["hydrogen_flow"] for v in rows]
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / sum(
        (a - mx) ** 2 for a in x
    )
    intercept = my - slope * mx
    assert r["parameters"]["slope_kg_per_kwh"] == pytest.approx(slope, abs=1e-14)
    assert r["parameters"]["intercept_kgph"] == pytest.approx(intercept, abs=1e-14)
    assert slope == pytest.approx(0.015057457386370935)
    assert r["statistics"]["evaluation"]["rmse"] == pytest.approx(0.011992736011982235)
    assert r["dataset"]["data"]["samples"] == 15068
    assert len({x["segment"] for x in rows}) == 8
    assert sum(s["samples"] for s in r["dataset"]["data"]["segments"]) == 15068
    assert r["query"]["predicted"] == pytest.approx(slope * 45 + intercept)
    for row in r["rows"]:
        assert row["system_power"] == pytest.approx(
            row["smps_power"] + row["subsystem_power"] + row["chiller_power"]
        )
        assert row["stop_index"] - row["first_index"] == row["n"]
    assert r["dataset"]["timing"].find("timezone unspecified") >= 0


@pytest.mark.parametrize("power", ["system_power", "stack_power"])
@pytest.mark.parametrize("channel", ["hydrogen_flow", "hydrogen_flow_cs"])
@pytest.mark.parametrize("model", ["affine", "constant-specific"])
def test_boundary_choices_and_joint_sensitivity(power, channel, model):
    r = service.calculate(
        dict(profile="csu-pem", power=power, channel=channel, model=model, flow_offset_bound=0.01)
    )
    assert r["inputs"]["power"] == power and r["inputs"]["channel"] == channel
    assert all(c["n"] == 8 for c in r["comparisons"])
    variants = r["sensitivity"]["parameter_vectors"]
    assert len(variants) == 8
    for point in r["curve"]:
        predictions = [v["coefficients"][0] * point["x"] + v["coefficients"][1] for v in variants]
        assert point["low"] == min(predictions) and point["high"] == max(predictions)
        assert point["measurement_low"] <= point["measurement_high"]
    if model == "constant-specific":
        assert r["parameters"]["intercept_kgph"] == 0


def test_evaluation_data_cannot_change_fit_or_sensitivity():
    p = service.profile("csu-pem")
    r = models.pem(p, models.PEMRequest())
    for row in p["data"]["rows"]:
        if row["split"] == "evaluation":
            row["hydrogen_flow"] += 100
    other = models.pem(p, models.PEMRequest())
    assert other["parameters"] == r["parameters"]
    assert other["sensitivity"] == r["sensitivity"]
    assert other["statistics"]["development"] == r["statistics"]["development"]
    assert other["statistics"]["evaluation"] != r["statistics"]["evaluation"]


def test_reactor_independent_analytic_expectations_and_reference_fit():
    r = service.calculate({"profile": "kit-slurry"})
    p = r["parameters"]
    b = p["baseline_c"]
    a = p["increment_k"]
    tau = p["tau_minutes"]
    assert tau == pytest.approx(9.299393265602896, rel=1e-5)
    assert r["statistics"]["descriptive"]["rmse"] == pytest.approx(0.48978657776031503)
    assert models.step_temperature(5, [b, a, tau]) == b
    assert models.step_temperature(5 + tau, [b, a, tau]) == pytest.approx(
        b + a * (1 - math.exp(-1))
    )
    # Equivalent incremental relaxation, not a second implementation of the fit.
    before = float(models.step_temperature(10, [b, a, tau]))
    assert models.step_temperature(20, [b, a, tau]) == pytest.approx(
        (b + a) + (before - b - a) * math.exp(-10 / tau)
    )
    assert all(
        a["predicted"] <= b["predicted"] for a, b in zip(r["curve"], r["curve"][1:], strict=False)
    )
    assert r["sensitivity"]["replicates"] == 64
    assert (
        r["sensitivity"]["parameter_vectors"]
        == service.calculate({"profile": "kit-slurry"})["sensitivity"]["parameter_vectors"]
    )
    assert "evaluation" not in r["statistics"]
    assert any(c["outcome"] == "missing" for c in r["claims"])
    for row in r["rows"]:
        assert row["x"] == pytest.approx((row["x_pixel"] - 174) * 8 / 73)
        assert row["observed"] == pytest.approx(260 + (358 - row["y_pixel"]) * 5 / 14)


@pytest.mark.parametrize(
    "inputs",
    [
        dict(profile="csu-pem", query_kw=0),
        dict(profile="csu-pem", query_kw=99),
        dict(profile="csu-pem", query_kw=float("nan")),
        dict(profile="csu-pem", power="dc_bus"),
        dict(profile="csu-pem", startup_seconds=0),
        dict(profile="kit-slurry", ambient_ua=0.08),
        dict(profile="kit-slurry", query_minutes=41),
        dict(profile="kit-slurry", digitization_bound_k=-1),
        dict(profile="csu-pem", flow_offset_bound=float("inf")),
        dict(profile="unknown"),
    ],
)
def test_unsupported_domains_and_silent_transfers_rejected(inputs):
    with pytest.raises(ValueError):
        service.calculate(inputs)


def test_zero_digitization_has_no_perturbation_but_does_not_claim_certainty():
    r = service.calculate(dict(profile="kit-slurry", digitization_bound_k=0))
    assert r["sensitivity"]["replicates"] == 1
    assert all(p["low"] == p["high"] == p["predicted"] for p in r["curve"])
    assert "Not quantified" in r["uncertainty"]["transfer"]


def test_immutable_results_export_restore_and_historical_identity(tmp_path, monkeypatch):
    store = Store(tmp_path / "original")
    before = store.list("project")
    result = equipment.perform(store, "equipment-literature-run", None, dict(profile="csu-pem"))
    assert store.list("project") == before
    original = deepcopy(store.get("literature-experiment", result["id"]))
    second = service.evaluate(store, dict(profile="csu-pem", query_kw=50))
    assert second["id"] != result["id"] and second["parameters"] == result["parameters"]
    pub = reporting.publish(store, "literature-experiment", result["id"])
    html = open(pub["path"]).read()
    assert "Reference-device experiment" in html and "Startup" in html
    bundle = reporting.bundle(store, pub["publication_id"])
    import zipfile

    with zipfile.ZipFile(bundle["path"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["omissions"]) == 8
    restored = Store(tmp_path / "restored")
    reporting.restore(bundle["path"], restored)
    assert restored.get("literature-experiment", result["id"]) == original
    assert restored.read_raw(original["capsule_raw_sha256"]) == store.read_raw(
        original["capsule_raw_sha256"]
    )
    assert "Current" in service.current(restored, result["id"])["applicability"]
    monkeypatch.setattr(service, "LOADED_SOURCE", dict(content_hash="new version"))
    assert "Historical" in service.current(restored, result["id"])["applicability"]
    assert store.get("literature-experiment", result["id"]) == original


def make_raw(directory):
    """Independently constructed four-plateau signals; deliberate startup exclusion."""
    signals = {c: [] for c in (*adapters.CHANNELS, "timestamp")}
    from datetime import datetime, timedelta

    for i in range(3700):
        power = 0 if i < 100 else (i - 100) // 900 + 1
        values = dict(
            power_command=power,
            stack_power=power,
            smps_power=power + 1,
            subsystem_power=2,
            chiller_power=3,
            hydrogen_flow=power * 0.2,
            hydrogen_flow_cs=power * 0.2 + 0.1,
            timestamp=(datetime(2025, 1, 1) + timedelta(seconds=i)).strftime("%d-%b-%Y %H:%M:%S"),
        )
        for c, v in values.items():
            signals[c].append(str(v))
    sources = []
    for c, values in signals.items():
        data = ("\n".join(values) + "\n").encode()
        (directory / c).write_bytes(data)
        sources.append(dict(channel=c, filename=c, sha256=hashlib.sha256(data).hexdigest()))
    return sources


def test_raw_mapping_hashes_interval_selection_and_corruption(tmp_path):
    sources = make_raw(tmp_path)
    r = adapters.pem(tmp_path, sources)
    assert r["samples"] == 3700 and r["retained_samples"] == 3120
    assert len(r["rows"]) == 8 and not r["segments"][0]["retained"]
    assert r["rows"][0]["first_index"] == 220 and r["rows"][0]["stop_index"] == 610
    assert r["rows"][0]["system_power"] == 7 and r["rows"][0]["hydrogen_flow"] == pytest.approx(0.2)
    assert r["rows"][1]["first_index"] == 610 and r["rows"][1]["stop_index"] == 1000
    (tmp_path / "chiller_power").write_text("bad")
    with pytest.raises(ValueError, match="Source bytes differ"):
        adapters.pem(tmp_path, sources)


def test_missing_time_is_not_filled(tmp_path):
    sources = make_raw(tmp_path)
    p = tmp_path / "timestamp"
    raw = p.read_bytes().replace(b"00:00:01", b"00:00:02")
    p.write_bytes(raw)
    next(s for s in sources if s["channel"] == "timestamp")["sha256"] = hashlib.sha256(
        raw
    ).hexdigest()
    with pytest.raises(ValueError, match="consecutive"):
        adapters.pem(tmp_path, sources)


def test_dataset_identity_and_parameters_retained_without_network(tmp_path, monkeypatch):
    import socket

    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("unexpected network")
    )
    catalogue = service.catalogue(Store(tmp_path))
    assert len(catalogue["profiles"]) == 2
    for name in service.PROFILES:
        r = service.calculate({"profile": name})
        assert digest(r["dataset"]) == r["dataset_id"]
        assert r["dataset"]["version"] == "reference-dataset/1"
        assert r["model_identity"].endswith("/1")


def test_narrative_review_detects_adapter_or_dataset_drift(tmp_path, monkeypatch):
    store = Store(tmp_path)
    saved = service.evaluate(store, {"profile": "csu-pem"})
    service.check_review()
    files = dict(service.LOADED_FILES)
    files["methane/literature/models.py"] += b"\n# Changed mechanics\n"
    monkeypatch.setattr(service, "LOADED_FILES", files)
    with pytest.raises(ValueError, match="need review"):
        service.calculate({"profile": "csu-pem"})
    assert store.get("literature-experiment", saved["id"])["parameters"] == saved["parameters"]


def test_changed_dataset_does_not_relabel_original_result(tmp_path, monkeypatch):
    store = Store(tmp_path)
    saved = service.evaluate(store, {"profile": "csu-pem"})
    files = dict(service.LOADED_FILES)
    data = json.loads(files["docs/reference-data/csu-pem.json"])
    data["data"]["rows"][0]["hydrogen_flow"] += 0.1
    files["docs/reference-data/csu-pem.json"] = json.dumps(data).encode()
    monkeypatch.setattr(service, "LOADED_FILES", files)
    assert service.current(store, saved["id"])["applicability"].startswith("Historical")
    with pytest.raises(ValueError, match="need review"):
        service.check_review()
