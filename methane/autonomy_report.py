"""Readable recorded beliefs and planning limitations; never recomputes decisions."""

import base64
import html
import json

from methane.provenance import LOADED_FILES


def report_html(result):
    font = base64.b64encode(LOADED_FILES["assets/fonts/DepartureMono-Regular.woff2"]).decode()
    sections = []
    for name, rows in result["records"].items():
        for row in rows:
            belief = row["decision"].get("uncertainty_beliefs")
            if belief is None:
                continue
            displayed = dict(belief["durations"])
            for asset, groups in belief.get("equipment_durations", {}).items():
                displayed.update(
                    {asset + " / " + k: v for k, v in groups.items() if v["independent_jobs"]}
                )
            duration = "".join(
                "<tr><td>"
                + html.escape(k)
                + "</td><td>"
                + str(round(v["mean_factor"], 3))
                + "</td><td>"
                + str(v["bounds"])
                + "</td><td>"
                + str(v["completed_phases"])
                + " / "
                + str(v["censored_phases"])
                + "</td><td>"
                + html.escape(v["status"])
                + "</td></tr>"
                for k, v in displayed.items()
            )
            record = dict(
                beliefs=belief,
                service_control=row["decision"].get("service_control"),
                measurements=row["decision"].get("performance_estimates"),
                observed_durations=row["field_operations"].get("duration_observations"),
                requested=row["requested"],
                applied=row["applied"],
            )
            sections.append(
                "<section><h2>"
                + html.escape(name)
                + " · hour "
                + str(row["hour"])
                + "</h2><table><tr><th>Phase family</th><th>Mean factor</th><th>Assumed support</th><th>Completed / censored phases</th><th>Evidence</th></tr>"
                + duration
                + '</table><p><a href="#operands-'
                + html.escape(name)
                + "-"
                + str(row["hour"])
                + '">Recorded operands and planning outcomes</a></p><pre id="operands-'
                + html.escape(name)
                + "-"
                + str(row["hour"])
                + '">'
                + html.escape(json.dumps(record, indent=2, allow_nan=False))
                + "</pre></section>"
            )
    return (
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Recorded autonomous service evidence</title><style>@font-face{font-family:Departure;src:url(data:font/woff2;base64,'
        + font
        + ")}body{background:#202020;color:#ffad43;margin:4vh auto;max-width:1000px;padding:24px;font:14px/1.65 Departure,monospace}a{color:inherit}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #795424;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 monospace}section{margin:50px 0}</style><h1>Recorded autonomous service evidence</h1><p>These are the assumptions and observations available at each original decision. Interval-end duration packets become eligible at the following decision. Mean duration and finite scenario weights are model assumptions and updates, not calibrated confidence limits. Completed work is separate from verified recovery. The source archive retains retrospective physical truth separately.</p>"
        + "".join(sections)
    )
