"""Self-contained evaluation write-ups, with full operands and scoped evidence."""

import base64
import html
import json

from methane.provenance import LOADED_FILES


def document(value, title):
    e = html.escape
    font = base64.b64encode(LOADED_FILES["assets/fonts/DepartureMono-Regular.woff2"]).decode()
    cells = "".join(
        "<tr><td>"
        + "</td><td>".join(
            e(str(x)) for x in (k, m["mae"], m["coverage"], m["mean_width"], m["unavailable"])
        )
        + "</td></tr>"
        for k, m in value.get("comparisons", {}).items()
    )
    narrative = "".join(
        f"<h2>{e(k.replace('_', ' ').capitalize())}</h2><p>{e(text).replace(chr(10), '<br>')}</p>"
        for k, text in value.get("writeup", {}).items()
        if k != "title"
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{e(title)}</title>
<style>@font-face{{font-family:Departure;src:url(data:font/woff2;base64,{font})}}*{{box-sizing:border-box}}body{{margin:0;background:#202020;color:#dbc092;font:14px/1.8 Departure,monospace}}main{{max-width:1050px;margin:auto;padding:5vw}}h1,h2,a{{color:#ffb752;font-weight:normal}}h1{{font-size:30px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}}table{{border-collapse:collapse;width:100%}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #70502e}}.table{{overflow:auto}}</style>
<main><p>Dispatch Lab / Recorded estimator evaluation</p><h1>{e(title)}</h1><p>{e(value["status"])} · {e(value.get("reason", ""))}</p><p>{e(value["scope"])}</p>{narrative}
<h2>Held-out predictions</h2><div class="table"><table><tr><th>Estimator</th><th>Absolute error</th><th>Band coverage</th><th>Mean width</th><th>Unavailable</th></tr>{cells}</table></div>
<p>Errors use the target's recorded units. Bands are calibrated on validation errors; coverage is measured only on applicable test predictions. Unsupported cases are shown separately, never silently replaced by a prediction. Synthetic channels do not establish field identification.</p>
<h2>Decision consequences</h2><p>{e(value.get("decision_consequences", "No operating benefit has been inferred."))}</p>
<h2>Data, protocol and complete recorded operands</h2><p>Training features exclude the separate retrospective label store. A deployment is an explicit new experiment assumption; repricing or editing this report cannot retrain the model.</p><pre>{e(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))}</pre>
<p>Offline reading needs no network. Live fitting or a numerical rerun needs the saved source environment and permitted inputs.</p></main></html>"""
