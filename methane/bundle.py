"""Portable source/input/result bundles with distinct recorded playback and numerical reruns."""

import argparse
import base64
import gzip
import hashlib
import json
import zipfile
from itertools import chain
from pathlib import Path

from methane.bundle_runtime import check
from methane.evidence import load, publish_completed, staging
from methane.provenance import LOADED_FILES, verify
from methane.source_capsule import decode


def make(result, path):
    verify(result)
    capsule = result.get("provenance", {}).get("source_capsule")
    source = decode(capsule) if capsule else {}
    files = {"source/" + k: v for k, v in source.items()}
    files["recorded-run.json.gz"] = gzip.compress(
        json.dumps(result, allow_nan=False).encode(), mtime=0
    )
    files["checker/autonomy_reference.py"] = LOADED_FILES["methane/autonomy_reference.py"]
    files["checker/duration_reference.py"] = LOADED_FILES["methane/duration_reference.py"]
    files["checker/retrieval_reference.py"] = LOADED_FILES["methane/retrieval_reference.py"]
    files["checker/recovery_loop_reference.py"] = LOADED_FILES["methane/recovery_loop_reference.py"]
    files["checker/performance_reference.py"] = LOADED_FILES["methane/performance_reference.py"]
    files["checker/lifecycle_reference.py"] = LOADED_FILES["methane/lifecycle_reference.py"]
    files["checker/reference.py"] = LOADED_FILES["methane/reference.py"]
    files["checker/recovery_belief_reference.py"] = LOADED_FILES[
        "methane/recovery_belief_reference.py"
    ]
    files["check_bundle.py"] = LOADED_FILES["methane/bundle_runtime.py"]
    if any(
        row["decision"].get("performance_estimates")
        for rows in result["records"].values()
        for row in rows
    ):
        from methane.adaptation import report_html as performance_report

        files["performance-estimates.html"] = performance_report(result).encode()
    if any(
        r["decision"].get("uncertainty_beliefs")
        for rows in result["records"].values()
        for r in rows
    ):
        from methane.autonomy_report import report_html as autonomy_report

        files["autonomous-services.html"] = autonomy_report(result).encode()
    files["playback.html"] = playback(result, source or LOADED_FILES).encode()
    from methane.taxonomy import report as taxonomy_report

    files["site-catalogue.html"] = taxonomy_report(result).encode()
    if result.get("taxonomy"):
        files["site-catalogue.json"] = json.dumps(result["taxonomy"], allow_nan=False).encode()
    from methane.offline_model import pages

    if result["config"].get("service_economics") is not None:
        from methane.provenance import LOADED_CAPSULE
        from methane.service_economics import html_report, reprice_run

        costs = reprice_run(result, result["config"]["service_economics"])
        files["service-economics.html"] = html_report(costs).encode()
        files["service-economics.json"] = json.dumps(costs, allow_nan=False).encode()
        files["service-pricing-source.json"] = json.dumps(LOADED_CAPSULE).encode()
    files["README.txt"] = b"""Dispatch Lab reproduction bundle

Open playback.html locally for recorded play/pause/step/speed and inspection.
Open model-report.html for the saved model explanations, examples and calculations.
Open site-catalogue.html for original identities, relationships and service boundaries.
Older archives explicitly report an unavailable original catalogue.
Its linked pages and recorded calculation data are in model/. The current reading
and calculation source is in model-report-source.json, separate from original execution.
Check integrity and independently recalculate physical/economic balances, without dependencies or network:
  python -I -S check_bundle.py . --out offline-check.json

Original source and dependency lock are in source/ when source_status is captured.
A source hash alone is not recoverable source; older archives are explicitly marked unavailable.
Restore the recorded dependency versions (requires cached packages for offline use):
  uv sync --project source --locked --offline --no-dev
Then recompute decisions with the ORIGINAL source in a separate process:
  source/.venv/bin/python source/recompute.py recorded-run.json.gz recomputation.json
This writes a comparison; it does not overwrite the recorded run. Solver search and
hardware can change time-limited decisions. Recorded playback never reruns a solver.

The reference checker is independently implemented and versioned by its file hash.
Hashes detect modification, not authenticity. Numerical checks do not calibrate a plant.
"""
    # Source contains the rerun entry point captured with the executable code.
    manifest = dict(
        schema_version="dispatch-lab/reproduction-bundle/1",
        run_id=result["run_id"],
        source_status="captured" if source else "unavailable (archive contains hashes only)",
        source_capsule_sha256=capsule["sha256"] if capsule else None,
        environment=result.get("provenance", {}).get("environment"),
        files={},
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        staging(path) as temporary,
        zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as z,
    ):
        for name, value in chain(sorted(files.items()), pages(result)):
            if name in manifest["files"]:
                raise ValueError("Duplicate generated bundle member: " + name)
            z.writestr(name, value)
            manifest["files"][name] = hashlib.sha256(value).hexdigest()
        z.writestr("bundle.json", json.dumps(manifest, indent=2))
        z.close()
        return publish_completed(temporary, path)


def unpack(path, directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in z.infolist()) > 1_500_000_000:
            raise ValueError("Invalid or excessive bundle inventory")
        for name in names:
            relative = Path(name)
            target = root / relative
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in name
                or not target.resolve().is_relative_to(root.resolve())
                or target.is_symlink()
            ):
                raise ValueError("Invalid bundle member path")
        for name in names:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
    return root


def playback(result, assets):
    """Recorded UI using the existing renderer. Numerical alternatives need the restored app."""
    from methane.costing import reprice
    from methane.ui import playback_value

    value = playback_value(result, register_contexts=False)
    value["offline_mode"] = True
    # Include recorded plans for local inspection; trim full component evidence from predicted rows.
    for name, rows in value["records"].items():
        for i, row in enumerate(rows):
            source = result["records"][name][i]
            row["decision"]["plan"]["trajectory"] = [
                {
                    k: v
                    for k, v in r.items()
                    if k not in ("component_records", "battery_record", "audits")
                }
                for r in source["decision"]["plan"]["trajectory"]
            ]
            row["audits"] = source.get("audits", [])

    def get(name):
        return assets["assets/" + name].decode()

    template = get("methane.html").replace("<!-- SOLAR WORKSPACE -->", get("solar.html"))
    template = template.replace("/gradio_api/file=docs/components.md", "source/README.md")
    css = "\n".join(
        get(n)
        for n in ("app.css", "plant-motion.css", "plant-scene.css", "methane.css", "solar.css")
    )
    if "assets/field-scene.css" in assets:
        css += "\n" + get("field-scene.css")
    if "assets/taxonomy.html" in assets:
        template = template.replace("<!-- TAXONOMY WORKSPACE -->", get("taxonomy.html"))
        css += "\n" + get("taxonomy.css")
    font = base64.b64encode(assets["assets/fonts/DepartureMono-Regular.woff2"]).decode()
    script = get("playback.js").split("function frameAt")[0] + get("methane.js") + get("solar.js")
    if "assets/field-operations.js" in assets:
        script = get("field-operations.js") + script
    if "assets/service-alternatives.js" in assets:
        script = get("service-alternatives.js") + script
    if "assets/field-scene.js" in assets:
        script = get("field-scene.js") + script
    if "assets/taxonomy.js" in assets:
        script += get("taxonomy.js")
    props = json.dumps({"value": value, "economics": reprice(result)}, allow_nan=False).replace(
        "<", "\\u003c"
    )
    bootstrap = """
const props=DATA; const observers={};
function watch(key,callback){observers[key]=callback;}
function trigger(name,data){
 if(name==='select'){
  const r=props.value.records[data.controller][data.hour];
  props.decision_answer={...data,trajectory:r.decision.plan.trajectory,audits:r.audits,
   battery_trace:{status:'unavailable',note:'Full recorded inputs are in recorded-run.json.gz; restore the app for interactive lineage.'},
   component_traces:Object.fromEntries(['electrolyser','hydrogen','co2','reactor','solar'].map(k=>[k,{status:'unavailable',note:'Full recorded component inputs are in recorded-run.json.gz. Restore the bundled app for interactive lineage.'}])),
   economic_trace:{report_price_version:props.economics.report_price_version,report_service_price_version:props.economics.report_service_price_version,note:'Recorded cost report; original decisions remain frozen.'}};
  queueMicrotask(()=>observers.decision_answer?.());return;
 }
 if(['submit','apply','edit','expand','input'].includes(name))alert('Recorded offline playback. Restore the bundled app for configuration, reports and replanning.');
}
mountMethane(document.getElementById('player'),props,watch,trigger);
""".replace("DATA", props)
    return (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dispatch Lab / recorded offline playback</title><style>@font-face{font-family:"Departure Mono";src:url(data:font/woff2;base64,'
        + font
        + ")}body{margin:0;background:#202020;color:#ffa32d}"
        + css
        + '</style></head><body><div id="player">'
        + template
        + "</div><script>"
        + script
        + "\n"
        + bootstrap
        + "</script></body></html>"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--verify-in", type=Path)
    args = p.parse_args()
    path = make(load(args.archive), args.out)
    print(path)
    if args.verify_in:
        report = check(unpack(path, args.verify_in))
        print(json.dumps(report, indent=2))
        if report["status"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
