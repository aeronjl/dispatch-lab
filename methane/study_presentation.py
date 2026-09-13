"""Small, source-bound report views; original publications and attempts stay intact."""

import copy
import errno
import hashlib
import json
import os
import uuid
from functools import lru_cache
from pathlib import Path

from methane.provenance import LOADED_FILES, digest

VERSION = "dispatch-lab/study-presentation/1"
METRICS = (
    "methane_kg",
    "ending",
    "forced_downtime_hours",
    "total_eur",
    "assumed_contribution_eur",
    "utilisation",
    "curtailed_kwh",
    "reactor_starts",
    "electrolyser_starts",
    "limited_solves",
    "fallbacks",
)


def metric(value):
    result = {k: copy.deepcopy(value[k]) for k in METRICS if k in value}
    if "service_outcomes" in value:
        result["service_outcomes_available"] = bool(value["service_outcomes"])
    if "service_work" in value:
        work = value["service_work"] or {}
        result["service_work"] = {
            "orders": [
                {
                    k: row.get(k)
                    for k in ("id", "kind", "status", "completed_hour", "verified_at_hour")
                }
                for row in work.get("orders", [])
            ],
            "executive": {
                "resources": [
                    {k: row.get(k) for k in ("resource", "ending", "reserved", "unit")}
                    for row in (work.get("executive") or {}).get("resources", [])
                    if row["resource"].startswith(("stock:", "upstream:"))
                ]
            },
        }
    return result


def project(value):
    """Copy displayed operands; never recalculate outcomes or modify a publication."""
    result = {k: v for k, v in value.items() if k not in ("cases", "integrity_sha256")}
    result["cases"] = []
    for case in value["cases"]:
        entry = {
            k: v
            for k, v in case["entry"].items()
            if k not in ("metrics", "computation", "integrity_sha256", "uncertainty_trajectory")
        }
        if case["entry"].get("metrics") is not None:
            entry["metrics"] = {name: metric(m) for name, m in case["entry"]["metrics"].items()}
        entry["original_entry_integrity_sha256"] = case["entry"].get("integrity_sha256")
        result["cases"].append({**case, "entry": entry})
    result["presentation"] = {
        "version": VERSION,
        "original_report_integrity_sha256": value.get("integrity_sha256"),
        "context": "saved publication" if value.get("report_id") else "live attempt summary",
        "scope": "Display projection of recorded report and attempt data. Detailed service state and computation operands remain in their original case attempts and archives; no numerical rerun.",
    }
    # Callers may annotate withdrawal or current context without changing cached data.
    return copy.deepcopy(result)


def stamp(path):
    s = Path(path).stat()
    return (s.st_mtime_ns, s.st_size, s.st_ino)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified(path):
    value = json.loads(Path(path).read_text())
    if digest({k: v for k, v in value.items() if k != "integrity_sha256"}) != value.get(
        "integrity_sha256"
    ):
        raise ValueError("Published study report integrity failure")
    return value


def original_publication(path):
    value = verified(path)
    if (
        value.get("report_id") != Path(path).stem
        or value.get("edition_id") != Path(path).parent.parent.name
    ):
        raise ValueError("Publication belongs to another report or edition")
    return value


def write_derived(path, value):
    from methane.studies import write_once

    sealed = {**value, "integrity_sha256": digest(value)}
    path = Path(path)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".pending")
    try:
        # Publish only complete bytes. Multiple readers/processes may derive the
        # same immutable view together; nobody should see a partially written file.
        write_once(temporary, sealed)
        os.link(temporary, path)
    except FileExistsError:
        if verified(path) != sealed:
            raise ValueError("Conflicting derived study record; original retained") from None
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EROFS):
            raise
        # Read-only restored stores remain readable. This is an in-memory
        # derived view, never a claim that a new original artifact was saved.
    finally:
        if temporary.exists():
            temporary.unlink()
    return sealed


def index_path(path):
    return Path(path).parent.parent / "publication-index" / Path(path).name


def index_value(value, path):
    return {
        "version": "dispatch-lab/publication-index/1",
        "source_report_sha256": sha(path),
        "publication": {
            k: value[k]
            for k in (
                "report_id",
                "published_at",
                "status",
                "completed_cases",
                "total_cases",
                "completed_pairs",
                "total_pairs",
            )
            if k in value
        },
    }


def preserve_index(value, path):
    return write_derived(index_path(path), index_value(value, path))


@lru_cache(maxsize=128)
def _index(path, file_stamp, derived_stamp):
    target = index_path(path)
    if target.exists():
        index = verified(target)
        if index["source_report_sha256"] != sha(path):
            raise ValueError("Published study report differs from its preserved index")
        if index["publication"]["report_id"] != Path(path).stem:
            raise ValueError("Publication index belongs to another report")
        return index
    return preserve_index(original_publication(path), path)


def publication_index(path):
    path = Path(path)
    target = index_path(path)
    return _index(str(path), stamp(path), stamp(target) if target.exists() else None)


def publications(identifier, root):
    from methane.studies import location

    return sorted(
        [
            copy.deepcopy(publication_index(p)["publication"])
            for p in (location(identifier, root) / "reports").glob("*.json")
        ],
        key=lambda p: p["published_at"],
        reverse=True,
    )


def view_path(path):
    binding = hashlib.sha256(LOADED_FILES["methane/study_presentation.py"]).hexdigest()
    return Path(path).parent.parent / "presentations" / binding / Path(path).name


@lru_cache(maxsize=16)
def _view(path, file_stamp, derived_stamp):
    target = view_path(path)
    original_sha = sha(path)
    if target.exists():
        saved = verified(target)
        if saved["source_report_sha256"] != original_sha:
            raise ValueError("Published study report differs from its saved presentation")
        if saved["view"].get("report_id") != Path(path).stem:
            raise ValueError("Presentation belongs to another report")
        return saved["view"]
    value = original_publication(path)
    projected = project(value)
    write_derived(
        target, {"version": VERSION, "source_report_sha256": original_sha, "view": projected}
    )
    return projected


def published_view(identifier, root, report_id=None):
    from methane import studies

    summaries = publications(identifier, root)
    selected = (
        next((p for p in summaries if p["report_id"] == report_id), None)
        if report_id
        else next(iter(summaries), None)
    )
    if selected is None:
        if report_id:
            raise ValueError("Report revision unavailable")
        return project(studies.report(identifier, root))
    path = studies.location(identifier, root) / "reports" / (selected["report_id"] + ".json")
    target = view_path(path)
    result = copy.deepcopy(
        _view(str(path), stamp(path), stamp(target) if target.exists() else None)
    )
    studies.reporting_source(result, root)
    return result
