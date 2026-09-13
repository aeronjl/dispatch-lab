"""Immutable, self-contained write-ups and licence-aware reproduction bundles."""

import base64
import hashlib
import html
import json
import zipfile
from pathlib import Path

from methane.provenance import LOADED_FILES
from methane.siting.production import directory, inspect
from methane.siting.store import atomic, digest, encode


def document(value, title):
    esc = html.escape
    font = base64.b64encode(LOADED_FILES["assets/fonts/DepartureMono-Regular.woff2"]).decode()
    candidates = value.get("candidates", value.get("cases", []))
    rows = []
    for c in candidates:
        s = c.get("summary")
        rows.append(
            "<tr>"
            + "".join(
                "<td>" + esc(str(v)) + "</td>"
                for v in (
                    c.get("label", c.get("case_id", "")),
                    c.get("status", "complete" if s else "incomplete"),
                    c.get("completed_hours", 0),
                    round(s["methane_kg"], 2)
                    if s and s.get("methane_kg") is not None
                    else "Not calculated",
                    round(s["total_eur"], 2) if s and s["total_eur"] is not None else "Unpriced",
                    c.get("role", ""),
                )
            )
            + "</tr>"
        )
    encoded = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{esc(title)}</title><style>@font-face{{font-family:Departure;src:url(data:font/woff2;base64,{font})}}*{{box-sizing:border-box}}body{{margin:0;background:#202020;color:#dbb780;font:14px/1.8 Departure,monospace}}main{{max-width:1200px;margin:auto;padding:8vw 5vw}}h1,h2{{font-weight:normal;color:#ffb752}}h1{{font-size:34px;line-height:1.3}}a{{color:#ffb752}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;border-bottom:1px solid #695136;padding:12px;font-weight:normal}}.scroll{{overflow:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.8 Departure}}details{{margin:35px 0}}summary{{cursor:pointer}}.note{{border-left:2px solid #ffb752;padding-left:20px}}</style><main><p>Dispatch Lab / Recorded siting study</p><h1>{esc(title)}</h1><p class="note">A versioned model comparison. Resource data, site feasibility, controller behaviour and assumed cash flow have separate evidence boundaries. Missing cases and costs remain visible.</p><p>{esc(value.get("authored_conclusion", ""))}</p><div class="scroll"><table><thead><tr><th>Case</th><th>Status</th><th>Hours</th><th>Methane / kg</th><th>Allocated / EUR</th><th>Role</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div><h2>How to read this result</h2><p>Methane is modelled production. Hydrogen consumed by methanation is not a second product sale. Supplied CO₂ is not capture. Ending inventories are separate from output. A cash scenario reprices the physical trace without changing the original controller prices.</p><p>Ranges across declared scenarios are not probability intervals. The same numerical solver can return different feasible time-limited decisions; repetitions remain identifiable. Public land or infrastructure maps do not establish development rights or connection capacity.</p><h2>Recorded calculation and evidence</h2><p>The complete readable record below includes identities, assumptions, numerical operands, missing evidence and unsuccessful attempts. Live recalculation requires the saved application and permitted data.</p><pre>{esc(encoded)}</pre><p>Document content identity {digest(value)}.</p></main></html>"""


def publish(store, kind, key):
    if kind == "study":
        value = inspect(store, key)
        title = value["manifest"]["name"]
    elif kind == "recommendation":
        value = store.get(kind, key)
        title = value["title"]
    elif kind == "cashflow":
        value = store.get(kind, key)
        title = value["scenario"]["name"]
    else:
        raise ValueError("Unknown report type")
    publication = dict(schema_version="site-publication/1", kind=kind, source_id=key, record=value)
    rid = store.put("publication", publication)
    target = store.root / "reports" / (rid + ".html")
    atomic(target, document(value, title).encode())
    return dict(publication_id=rid, title=title, path=str(target))


def bundle(store, publication_id):
    publication = store.get("publication", publication_id)
    value = publication["record"]
    study_ids = (
        [publication["source_id"]]
        if publication["kind"] == "study"
        else value.get("study_ids", [value.get("study_id")])
    )
    files = {
        f"reports/{publication_id}.html": (store.root / "reports" / (publication_id + ".html")),
        "publication.json": encode(publication),
    }
    sources = set()
    omissions = []

    def add(kind, key):
        if not key:
            return None
        record = store.get(kind, key)
        files[f"{kind}/{key}.json"] = encode(record)
        return record

    def raw(key):
        files["raw/" + key] = store.root / "raw" / key

    for sid in filter(None, study_ids):
        study = add("study", sid)
        d = directory(store, sid)
        files[f"studies/{sid}/source-capsule.json"] = d / "source-capsule.json"
        for case in study["cases"]:
            design = add("design", case["design_id"])
            add("site", design["site_revision"])
            assessment = add("assessment", design.get("assessment_id"))
            if assessment:
                for layer in assessment.get("intersections", []):
                    if layer.get("source_id"):
                        sources.add(layer["source_id"])
            for eid in (design.get("utilities") or {}).get("evidence_ids", []):
                evidence = add("evidence", eid)
                if evidence.get("source_id"):
                    sources.add(evidence["source_id"])
            for eid in design["evidence_ids"]:
                e = add("evidence", eid)
                if e.get("source_id"):
                    sources.add(e["source_id"])
            env = add("environment", case["environment_id"])
            sources.update(env["source_ids"])
            permissions = [store.get("source", k)["redistribution"] for k in env["source_ids"]]
            if all(p == "permitted" for p in permissions):
                raw(env["normalized_sha256"])
            else:
                omissions.append(
                    dict(
                        kind="normalised environment",
                        id=case["environment_id"],
                        reason="One or more inputs lack redistribution permission; restore separately",
                    )
                )
            permitted = all(p == "permitted" for p in permissions)
            for path in sorted((d / case["case_id"]).glob("*.json")):
                if not permitted and path.name.startswith("entry-"):
                    omissions.append(
                        dict(
                            kind="recorded period and checkpoint",
                            id=path.name,
                            reason="Contains source observations and forecasts whose redistribution is unresolved",
                        )
                    )
                    continue
                files[f"studies/{sid}/{case['case_id']}/{path.name}"] = path
                if path.name.startswith("entry-"):
                    entry = json.loads(path.read_bytes())
                    if entry.get("summary_sha256"):
                        raw(entry["summary_sha256"])
                    raw(entry["checkpoint_sha256"])
                    raw(entry["period_sha256"])
                    from methane.siting.production import read_blob

                    period = read_blob(store, entry["period_sha256"])
                    for name, reference in period["references"].items():
                        # Weather embeds licensed normalised data; omit if rights are unresolved.
                        if name == "weather" and not all(p == "permitted" for p in permissions):
                            omissions.append(
                                dict(
                                    kind="period weather",
                                    id=reference,
                                    reason="Source redistribution unresolved",
                                )
                            )
                        else:
                            raw(reference)
        progress = d / "progress.json"
        if progress.exists():
            files[f"studies/{sid}/progress.json"] = progress
    for key in sources:
        source = add("source", key)
        if source["redistribution"] == "permitted":
            raw(source["raw_sha256"])
        else:
            omissions.append(
                dict(
                    kind="raw source",
                    id=key,
                    sha256=source["raw_sha256"],
                    reason=source["redistribution"],
                )
            )
    if publication["kind"] in ("cashflow", "recommendation"):
        add(publication["kind"], publication["source_id"])
    for key in value.get("cashflow_ids", []):
        add("cashflow", key)
    manifest = dict(
        schema_version="site-reproduction-bundle/1",
        publication_id=publication_id,
        omissions=omissions,
        offline_reproduction="complete within frozen model/data scope"
        if not omissions
        else "requires separately restored restricted inputs",
        files={k: file_hash(v) for k, v in files.items()},
        instructions="Restore with python -m methane.siting.reporting restore BUNDLE.zip --root NEW_STORE. Use the saved source capsule with uv sync --locked. Recorded playback uses partitions; a numerical rerun creates a new study edition. No network is needed to read this report.",
    )
    files["manifest.json"] = encode(manifest)
    destination = store.root / "exports" / (publication_id + ".zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            if isinstance(content, Path):
                z.write(content, name)
            else:
                z.writestr(name, content)
    temporary.replace(destination)
    return dict(path=str(destination), manifest=manifest)


def file_hash(value):
    if not isinstance(value, Path):
        return hashlib.sha256(value).hexdigest()
    with value.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def restore(path, store):
    """Verify an entire bundle before any append-only restoration; never execute its code."""
    from methane.siting.store import KINDS, identifier

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive members")
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("schema_version") != "site-reproduction-bundle/1" or set(names) != {
            "manifest.json",
            *manifest["files"],
        }:
            raise ValueError("Bundle inventory mismatch")
        targets = {}
        for name, expected in manifest["files"].items():
            parts = Path(name).parts
            if not parts or Path(name).is_absolute() or ".." in parts or "\\" in name:
                raise ValueError("Unsafe bundle path")
            with z.open(name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError("Bundle member integrity mismatch: " + name)
            if parts[0] == "raw" and len(parts) == 2:
                if identifier(parts[1]) != expected:
                    raise ValueError("Raw identity mismatch")
                target = store.root / name
            elif parts[0] in KINDS and len(parts) == 2:
                record = json.loads(z.read(name))
                if digest(record) != identifier(Path(parts[1]).stem):
                    raise ValueError("Record identity mismatch")
                target = store.path(parts[0], Path(parts[1]).stem)
            elif parts[0] == "studies" and len(parts) in (3, 4):
                identifier(parts[1])
                leaf = parts[-1]
                if len(parts) == 4:
                    import re

                    if not re.fullmatch(r"case-\d{3}", parts[2]) or not (
                        re.fullmatch(r"entry-\d{8}\.json", leaf)
                        or leaf in ("summary.json", "independent-checks.json")
                    ):
                        raise ValueError("Unknown study member")
                elif leaf not in ("progress.json", "source-capsule.json"):
                    raise ValueError("Unknown execution metadata")
                target = store.root / "execution" / Path(*parts[1:])
            elif parts[0] == "reports" and len(parts) == 2 and Path(parts[1]).suffix == ".html":
                identifier(Path(parts[1]).stem)
                target = store.root / name
            elif name == "publication.json":
                record = json.loads(z.read(name))
                if digest(record) != manifest["publication_id"]:
                    raise ValueError("Publication identity mismatch")
                target = store.path("publication", manifest["publication_id"])
            else:
                raise ValueError("Unsupported bundle member: " + name)
            if target.exists() and file_hash(target) != expected:
                raise ValueError(
                    "Restore would overwrite a different saved record; use a new store"
                )
            targets[name] = target
        # All hashes and conflicts checked first; one bounded file is resident at a time.
        for name, target in targets.items():
            if not target.exists():
                atomic(target, z.read(name))
        return dict(
            publication_id=manifest["publication_id"],
            restored_files=len(targets),
            omissions=manifest["omissions"],
            root=str(store.root),
        )


if __name__ == "__main__":
    import argparse

    from methane.siting.store import Store

    parser = argparse.ArgumentParser(description="Verify and restore a Sites bundle offline")
    parser.add_argument("command", choices=["restore"])
    parser.add_argument("bundle")
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    print(json.dumps(restore(args.bundle, Store(args.root)), indent=2))
