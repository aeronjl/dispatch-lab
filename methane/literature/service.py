"""Versioned reference experiments, immutable results and read-only source context."""

import hashlib
import json
from datetime import UTC, datetime

from methane.literature import models
from methane.provenance import LOADED_CAPSULE, LOADED_FILES, LOADED_SOURCE
from methane.siting.store import digest, encode

PROFILES = ("csu-pem", "kit-slurry")
BOUNDARY = (
    "Reference-device experiment, independent of the selected project or run. "
    "Numerical fit, evidence applicability and plant transfer are separate claims. "
    "No project parameters, dispatch decisions or original research results are changed."
)


def review_bindings():
    paths = (
        "methane/literature/adapters.py",
        "methane/literature/models.py",
        "docs/literature-models.md",
    )
    return {
        name: {
            p: hashlib.sha256(LOADED_FILES[p]).hexdigest()
            for p in (*paths, f"docs/reference-data/{name}.json")
        }
        for name in PROFILES
    }


def check_review():
    saved = json.loads(LOADED_FILES.get("docs/reference-data/review.json", b"{}"))
    if saved.get("bindings") != review_bindings():
        raise ValueError(
            "Reference experiment explanations need review against the current adapters and datasets"
        )


def profile(name):
    if name not in PROFILES:
        raise ValueError("Unknown reference dataset")
    return json.loads(LOADED_FILES[f"docs/reference-data/{name}.json"])


def catalogue(store):
    return dict(
        context="Current model · source-device experiments",
        boundary=BOUNDARY,
        profiles=[dict(**profile(k), dataset_id=digest(profile(k))) for k in PROFILES],
        defaults={
            "csu-pem": models.PEMRequest().model_dump(),
            "kit-slurry": models.ReactorRequest().model_dump(),
        },
        results=[
            {k: r[k] for k in ("id", "title", "created_at", "inputs", "model_identity")}
            for r in store.list("literature-experiment")
        ],
    )


def calculate(data):
    check_review()
    inputs = models.request(data)
    p = profile(inputs.profile)
    result = (models.pem if inputs.profile == "csu-pem" else models.reactor)(p, inputs)
    return dict(
        version="literature-experiment/1",
        title=p["title"],
        inputs=inputs.model_dump(),
        dataset_id=digest(p),
        dataset=p,
        boundary=BOUNDARY,
        **result,
        implementation_source=LOADED_SOURCE["content_hash"],
        uncertainty=dict(
            measurement=p["measurement_uncertainty"],
            parameter=result["sensitivity"]["scope"],
            structural="PEM: compare affine and constant-specific forms on the same inputs. Reactor: one first-order approximation only; omitted mechanisms remain unknown.",
            transfer="Not quantified. Source-device coefficients are unavailable for plant dispatch or automatic capacity scaling.",
        ),
    )


def evaluate(store, data):
    value = calculate(data)
    value.update(
        created_at=datetime.now(UTC).isoformat(),
        capsule_raw_sha256=store.raw(encode(LOADED_CAPSULE)),
    )
    return dict(id=store.put("literature-experiment", value), **value)


def current(store, key):
    value = store.get("literature-experiment", key)
    matching = value["implementation_source"] == LOADED_SOURCE["content_hash"] and value[
        "dataset_id"
    ] == digest(profile(value["inputs"]["profile"]))
    return dict(
        id=key,
        **value,
        applicability="Current source and dataset"
        if matching
        else "Historical source or dataset; original result retained",
    )


def perform(store, operation, key, data):
    if operation == "equipment-literature-catalogue":
        return catalogue(store)
    if operation == "equipment-literature-run":
        return evaluate(store, data)
    if operation == "equipment-literature-result":
        return current(store, key)
    raise ValueError("Unknown reference-experiment operation")


def report_html(value):
    from html import escape

    def esc(v):
        return escape(str(v))

    p = value["dataset"]
    out = "<h2>Reference-device experiment</h2><p>" + esc(value["boundary"]) + "</p>"
    out += "<p>" + esc(p["conditions"]) + "</p><p>" + esc(p["timing"]) + "</p>"
    out += "<p>" + esc(p["protocol_status"]) + "</p><p>" + esc(value["equation"]) + "</p>"
    out += (
        "<h3>Original inputs and fitted parameters</h3><pre>"
        + esc(
            json.dumps(
                dict(inputs=value["inputs"], parameters=value["parameters"], query=value["query"]),
                indent=2,
            )
        )
        + "</pre>"
    )
    out += (
        "<h3>Discrepancies · "
        + esc(value["unit"])
        + "</h3><table><tr><th>Subset</th><th>Count</th><th>Bias</th><th>RMSE</th></tr>"
    )
    for name, s in value["statistics"].items():
        out += f"<tr><td>{esc(name)}</td><td>{s['n']}</td><td>{s['bias']:.6g}</td><td>{s['rmse']:.6g}</td></tr>"
    out += "</table><h3>Scope of evidence</h3>"
    for c in value["claims"]:
        out += (
            "<p>" + esc(c["claim"]) + ": " + esc(c["outcome"]) + ". " + esc(c["method"]) + ".</p>"
        )
    for name, note in value["uncertainty"].items():
        out += "<p>" + esc(name) + ": " + esc(note) + "</p>"
    out += "<h3>Paired points</h3><table><tr><th>Subset</th><th>Input</th><th>Observed</th><th>Predicted</th><th>Residual</th></tr>"
    for r in value["rows"]:
        out += (
            "<tr>"
            + "".join(
                "<td>" + esc(r[k]) + "</td>"
                for k in ("split", "x", "observed", "predicted", "residual")
            )
            + "</tr>"
        )
    out += "</table><h3>Sources and identity</h3>"
    for source in p["sources"]:
        out += '<p><a href="' + esc(source["url"]) + '">' + esc(source["title"]) + "</a></p>"
    out += (
        "<p>Dataset "
        + esc(value["dataset_id"])
        + "; model "
        + esc(value["model_identity"])
        + "; implementation "
        + esc(value["implementation_source"])
        + ".</p>"
    )
    out += "<p>Compact observations, inputs, fits, joint parameter scenarios and source metadata are retained in the bundle. Original raw source files are not included; full preprocessing requires their separately restored, verified bytes.</p>"
    return out
