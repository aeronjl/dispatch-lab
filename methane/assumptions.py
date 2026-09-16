"""Read-only, version-bound assumption review. Never changes a simulation input."""

import copy
import hashlib
import json
from dataclasses import asdict
from functools import lru_cache

VERSION = "dispatch-lab/assumption-review/1"
REGISTRY = "docs/assumption-review.json"


def reference_configuration():
    """Schema coverage includes optional examples; it does not enable them."""
    from methane.config import Config
    from methane.integration import Integration
    from methane.recovery import RecoveryPolicy
    from methane.service_economics import ACTIVITY_VERSION, illustrative
    from methane.services.configuration import ServiceSystem
    from methane.services.controller import ServicePolicy
    from methane.services.investigator import InvestigationPolicy
    from methane.solar_model import default_design

    c = Config()
    value = c.to_dict()
    value["plant"]["integration"] = Integration().model_dump()
    value.update(
        service_system=asdict(ServiceSystem()),
        recovery_policy=asdict(RecoveryPolicy()),
        service_policy=asdict(ServicePolicy()),
        investigation_policy=asdict(InvestigationPolicy()),
        solar=default_design(c.plant, c.weather),
        service_economics=illustrative(c.costs, version=ACTIVITY_VERSION),
    )
    from methane.lifecycle.configuration import Outage
    from methane.lifecycle.fixtures import illustrative as lifecycle_fixture

    value["lifecycle"] = lifecycle_fixture(c).lifecycle
    value["lifecycle"]["outages"] = [
        Outage(resource="access", start_hour=12, end_hour=18).model_dump(mode="json")
    ]
    return value


def flatten(value, prefix=""):
    """Use [] for repeated objects, retaining distinct values and list order."""
    if isinstance(value, dict):
        return {
            p: v
            for k, x in value.items()
            for p, v in flatten(x, f"{prefix}.{k}".strip(".")).items()
        }
    if isinstance(value, (list, tuple)):
        result = {}
        for item in value:
            for path, leaf in flatten(item, prefix + ".[]").items():
                result.setdefault(path, []).append(leaf)
        return result
    return {prefix: value}


@lru_cache(maxsize=1)
def _registry():
    from methane.provenance import LOADED_FILES

    return json.loads(LOADED_FILES[REGISTRY])


def registry():
    return copy.deepcopy(_registry())


def freshness(review=None, files=None):
    from methane.provenance import LOADED_FILES

    review = review or _registry()
    files = LOADED_FILES if files is None else files
    return {
        key: "reviewed"
        if all(
            hashlib.sha256(files.get(path, b"")).hexdigest() == expected
            for path, expected in group["bindings"].items()
        )
        else "stale"
        for key, group in review["groups"].items()
    }


def validate(review=None):
    review = review or _registry()
    expected = flatten(reference_configuration())
    actual = {p["path"]: p for p in review["parameters"]}
    if len(actual) != len(review["parameters"]) or actual.keys() != expected.keys():
        raise ValueError(
            f"Assumption inventory changed: missing {expected.keys() - actual.keys()}, removed {actual.keys() - expected.keys()}"
        )
    if any(p["reference_default"] != expected[k] for k, p in actual.items()):
        raise ValueError("Assumption reference defaults changed; review required")
    for p in actual.values():
        if p["group"] not in review["groups"] or p["category"] not in review["categories"]:
            raise ValueError("Unbound assumption classification")
    for group in review["groups"].values():
        if not group["bindings"] or any(s not in review["sources"] for s in group["sources"]):
            raise ValueError("Missing assumption source or implementation binding")
        for path in group["checks"]:
            from methane.provenance import LOADED_FILES

            if path not in LOADED_FILES:
                raise ValueError("Missing verification reference: " + path)
    if "stale" in freshness(review).values():
        raise ValueError("Assumption mechanism reviews are stale")
    return True


def snapshot(config):
    """Captured within new taxonomy snapshots, once per run. Legacy snapshots stay absent."""
    from methane.provenance import LOADED_SOURCE, digest

    review = registry()
    statuses = freshness(review)
    from methane.uncertainty import catalogue as uncertainty_catalogue

    uncertainties = {p["path"]: p for p in uncertainty_catalogue(config)["parameters"]}
    current = flatten(config)
    known = {p["path"] for p in review["parameters"]}
    # Null optional blocks represent absence, not unreviewed leaf parameters.
    unknown = [p for p in current if p not in known and current[p] is not None]
    for p in review["parameters"]:
        p["uncertainty"] = uncertainties[p["path"]]
        p["present"] = p["path"] in current
        p["value"] = current.get(p["path"])
        p["review_status"] = statuses[p["group"]]
    for key, group in review["groups"].items():
        group["review_status"] = statuses[key]
    review.update(
        source=LOADED_SOURCE["content_hash"],
        config_hash=digest(config),
        unreviewed_paths=unknown,
        context="Current review of the supplied configuration; reference defaults do not replace missing recorded values.",
    )
    review["content_hash"] = digest(review)
    return review


def for_topic(review, topic):
    if not review:
        return None
    groups = {k: g for k, g in review["groups"].items() if topic in g["topics"]}
    return {
        "edition": review["edition"],
        "groups": groups,
        "parameters": [p for p in review["parameters"] if p["group"] in groups],
        "sources": {s: review["sources"][s] for g in groups.values() for s in g["sources"]},
        "scope": review["scope"],
    }


if __name__ == "__main__":
    validate()
    print(
        f"Reviewed {len(_registry()['parameters'])} parameter paths and {len(_registry()['groups'])} mechanism groups; no claim of plant calibration."
    )


def report_html(review, *, source_details=True):
    """Self-contained readable evidence, using the supplied snapshot only."""
    import html

    esc = html.escape
    if not review:
        return "<section><h2>Assumption review</h2><p>No original assumption review was saved with this catalogue. Current review is available only through an explicitly labelled context change.</p></section>"
    out = [
        f'<section id="assumption-review"><h2>Assumptions and evidence · {esc(review["edition"])}</h2><p>{esc(review["scope"])}</p><p>{esc(review["calibration_gate"])}</p>'
    ]
    for key, g in review["groups"].items():
        out += [
            f'<article id="assumption-{esc(key)}"><h3>{esc(g["title"])}</h3><p>{esc(g["evidence_status"])} · review {esc(g.get("review_status", "recorded"))}</p>',
            f"<p>{esc(g['mechanism'])}</p><p><strong>Limit:</strong> {esc(g['boundary'])}</p><p><strong>Evidence needed:</strong> {esc(g['next_data'])}</p>",
        ]
        for s in g["sources"]:
            ref = review["sources"][s]
            link = (
                f'<a href="{esc(ref["url"], quote=True)}">{esc(ref["title"])}</a>'
                if ref["url"].startswith("https://")
                else esc(ref["title"])
            )
            details = (
                f" — {esc(ref['finding'])} {esc(ref['applicability'])}" if source_details else ""
            )
            out.append(f"<p>{link}{details}</p>")
        out.append(
            "<table><thead><tr><th>Parameter</th><th>Recorded value / reference</th><th>Evidence</th></tr></thead><tbody>"
        )
        for p in review["parameters"]:
            if p["group"] != key:
                continue
            value = (
                p.get("value")
                if p.get("present")
                else "Unavailable; reference "
                + json.dumps(p["reference_default"], ensure_ascii=False)
            )
            out.append(
                f"<tr><td>{esc(p['path'])}<br>{esc(p['unit'])}</td><td>{esc(str(value))}</td><td>{esc(p['category'])} · {esc(p['evidence_status'])}<br>{esc(p.get('sensitivity_scope', p['range_note']))}<br>Uncertainty: {esc(p.get('uncertainty', {}).get('representation', 'No original uncertainty contract'))}</td></tr>"
            )
        out.append("</tbody></table></article>")
    out.append("</section>")
    return "".join(out)
