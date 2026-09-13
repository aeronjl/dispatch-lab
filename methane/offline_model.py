"""Paged, network-free reading of original model records and derived calculations.

No solver or learning fixture runs here. The complete source recording remains
linked; calculated reports identify the current derivation separately.
"""

import hashlib
import html
import json
import posixpath
from pathlib import Path
from urllib.parse import quote, urlsplit

from methane.provenance import LOADED_CAPSULE, LOADED_FILES, LOADED_SOURCE, digest

VERSION = "dispatch-lab/offline-model-pages/1"
CSS = """@font-face{font-family:Departure;src:url(DepartureMono-Regular.woff2)}
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#222220;color:#ffc579;font:15px/1.8 Departure,monospace}
main,nav{max-width:1080px;margin:auto;padding:28px 24px}nav{display:flex;gap:22px;flex-wrap:wrap;border-bottom:1px solid #735e40;font-size:12px}
a{color:inherit;text-underline-offset:4px}a:focus-visible,.table-scroll:focus-visible{outline:2px solid #ffc579;outline-offset:4px}
h1{font-size:32px;line-height:1.4}h2{font-size:23px;margin-top:44px}h3{font-size:18px}p,li{max-width:88ch}li{margin:10px 0}
section{margin:38px 0;padding-top:18px;border-top:1px solid #735e40}.context{font-size:12px;color:#cfb087;overflow-wrap:anywhere}
.equation{padding:14px;border-left:2px solid #a97436;overflow-wrap:anywhere}.table-scroll{overflow:auto;margin:24px 0}
table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid #655239;padding:10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{font-weight:normal}td:first-child{min-width:180px;max-width:400px}
code,pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}.index-table{min-width:650px}.pagination{display:flex;gap:24px;margin:28px 0}
@media(max-width:600px){body{font-size:14px}main,nav{padding:20px 18px}h1{font-size:26px}h2{font-size:21px}td:first-child{min-width:120px}}
"""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def link(page, target, label):
    relative = posixpath.relpath(target, posixpath.dirname(page) or ".")
    return (
        '<a href="'
        + html.escape(quote(relative, safe="/.-_"), quote=True)
        + '">'
        + html.escape(str(label))
        + "</a>"
    )


def flatten(value, prefix=""):
    if isinstance(value, dict):
        if not value:
            yield prefix, "{}"
        for key, item in value.items():
            yield from flatten(item, f"{prefix} / {key}" if prefix else str(key))
    elif isinstance(value, (list, tuple)):
        if not value:
            yield prefix, "[]"
        for i, item in enumerate(value):
            yield from flatten(item, f"{prefix} / {i}")
    else:
        yield prefix, "Undefined" if value is None else str(value)


def rows(value):
    nodes = (
        value.get("nodes") or value.get("report", {}).get("lineage", {}).get("nodes", [])
        if isinstance(value, dict)
        else []
    )
    if nodes:
        for node in nodes:
            label = str(node.get("label", node["id"]))
            yield (
                label,
                ("Undefined" if node["value"] is None else str(node["value"]))
                + " "
                + str(node.get("unit", "")),
            )
            for key in ("id", "formula", "source", "inputs", "parents"):
                if node.get(key) is not None:
                    yield from flatten(node[key], label + " / " + key)
        # Status, assumptions and accounting qualifications remain readable.
        for key in (
            "status",
            "note",
            "boundary",
            "report_source_content_hash",
            "dispatch_source_content_hash",
            "model",
            "implementation_id",
            "source_content_hash",
            "implementation_file",
            "implementation_file_sha256",
            "record_path",
            "record_sha256",
            "decision_path",
            "observed_nodes",
            "observation_provenance",
            "audits",
        ):
            if key in value:
                yield from flatten(value[key], key)
    else:
        yield from flatten(value)


def table_chunks(values):
    """Bound each readable page without truncating long recorded strings."""
    chunk, count, size = [], 0, 0
    for label, value in values:
        text = str(value)
        for i in range(0, max(1, len(text)), 2000):
            part = text[i : i + 2000]
            heading = str(label) + (f" / continued {i // 2000 + 1}" if i else "")
            row = "<tr><td>" + html.escape(heading) + "</td><td>" + html.escape(part) + "</td></tr>"
            if chunk and (count >= 160 or size + len(row.encode()) > 96000):
                yield "".join(chunk)
                chunk, count, size = [], 0, 0
            chunk.append(row)
            count += 1
            size += len(row.encode())
    if chunk:
        yield "".join(chunk)


def table(body):
    return (
        '<div class="table-scroll" tabindex="0" aria-label="Scrollable recorded values"><table><thead><tr><th>Quantity or recorded field</th><th>Value, units and transformation</th></tr></thead><tbody>'
        + body
        + "</tbody></table></div>"
    )


def original_reference(doc, details):
    if not doc:
        return "<p>Original explanations unavailable for this archive. Current explanations have not been substituted.</p>"
    result = []
    for key, topic in doc.get("topics", {}).items():
        body = (
            '<section id="'
            + html.escape(key, quote=True)
            + '"><h2>'
            + html.escape(topic["title"])
            + "</h2><p>"
            + html.escape(topic["purpose"])
            + "</p>"
        )
        for passage in topic["passages"]:
            body += (
                "<h3>"
                + html.escape(passage["title"])
                + "</h3><p>"
                + html.escape(passage["text"])
                + "</p>"
            )
            if passage.get("equation"):
                body += '<p class="equation">' + html.escape(passage["equation"]) + "</p>"
        for heading, values in (
            ("Assumptions", [a["text"] for a in topic["assumptions"]]),
            (
                "Evidence and its limits",
                [
                    c["claim"] + ": " + c["status"] + " — " + c.get("scope", "")
                    for c in topic["evidence"]
                ],
            ),
        ):
            body += (
                "<h3>"
                + heading
                + "</h3><ul>"
                + "".join("<li>" + html.escape(v) + "</li>" for v in values)
                + "</ul>"
            )
        body += (
            "<h3>Applicability and omitted behaviour</h3><p>"
            + html.escape(topic.get("limitations", "Original limitations unavailable"))
            + "</p><p>"
            + details[key]
            + "</p>"
        )
        body += (
            "<ul>"
            + "".join(
                '<li><a href="' + html.escape(u, quote=True) + '">' + html.escape(u) + "</a></li>"
                for u in topic["sources"]
                if u.startswith("https://")
            )
            + "</ul></section>"
        )
        result.append(body)
    return "".join(result)


class Report:
    def __init__(self, result, archive_href, source_href):
        for target in (archive_href, source_href):
            address = urlsplit(target)
            if (
                address.scheme
                or address.netloc
                or address.query
                or address.fragment
                or target.startswith("/")
                or "\\" in target
            ):
                raise ValueError("Offline report links must be relative bundle paths")
        self.result, self.archive_href, self.source_href = result, archive_href, source_href
        self.files = []

    def emit(self, path, content, kind):
        if isinstance(content, str):
            content = content.encode()
        self.files.append(
            dict(
                path=path, kind=kind, bytes=len(content), sha256=hashlib.sha256(content).hexdigest()
            )
        )
        return path, content

    def page(self, path, title, body):
        css = posixpath.relpath("model/report.css", posixpath.dirname(path) or ".")
        nav = " · ".join(
            (
                link(path, "model-report.html", "Model report"),
                link(path, "playback.html", "Recorded playback"),
                link(path, self.archive_href, "Complete original recording"),
                link(path, "model/manifest.json", "Report identities"),
            )
        )
        context = (
            "Run "
            + str(self.result["run_id"])
            + " · Original dispatch prices: "
            + str(self.result.get("decision_cost_version", "Unavailable"))
        )
        execution = self.result.get("provenance", {}).get("source", {}).get("content_hash")
        derivation = (
            "Original execution: "
            + (execution[:16] if execution else "source identity unavailable")
            + " · Reading and calculation implementation: "
            + LOADED_SOURCE["content_hash"][:16]
            + ". Full identities are linked above."
        )
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
            + html.escape(title)
            + ' · Dispatch Lab</title><link rel="stylesheet" href="'
            + html.escape(css, quote=True)
            + '"></head><body><nav aria-label="Report navigation">'
            + nav
            + "</nav><main><h1>"
            + html.escape(title)
            + '</h1><p class="context">'
            + html.escape(context)
            + '</p><p class="context">'
            + html.escape(derivation)
            + "</p>"
            + body
            + "</main></body></html>"
        )

    def tables(self, stem, title, value, note, data_target):
        chunks = list(table_chunks(rows(value))) or [
            "<tr><td>Status</td><td>No recorded operands</td></tr>"
        ]
        for i, chunk in enumerate(chunks):
            path = f"model/{stem}-{i + 1}.html"
            nav = (
                (link(path, f"model/{stem}-{i}.html", "Previous values") if i else "")
                + " "
                + (
                    link(path, f"model/{stem}-{i + 2}.html", "Next values")
                    if i + 1 < len(chunks)
                    else ""
                )
            )
            body = (
                "<p>"
                + html.escape(note)
                + "</p><p>"
                + link(path, data_target, "Complete calculation data and context")
                + '</p><p class="context">Part '
                + str(i + 1)
                + " of "
                + str(len(chunks))
                + "</p>"
                + table(chunk)
                + '<div class="pagination">'
                + nav
                + "</div>"
            )
            yield self.emit(path, self.page(path, title, body), "calculation")


def pages(
    result,
    *,
    archive_href="recorded-run.json.gz",
    source_href="model-report-source.json",
    include_source=True,
):
    """Yield a complete set of read-only pages; callers stream them to disk/ZIP."""
    from methane.documentation import calculation
    from methane.model_topics import TOPICS

    if include_source and source_href != "model-report-source.json":
        raise ValueError("An included renderer source uses model-report-source.json")
    book = Report(result, archive_href, source_href)
    yield book.emit("model/report.css", CSS, "style")
    for name in ("DepartureMono-Regular.woff2", "OFL.txt"):
        yield book.emit("model/" + name, LOADED_FILES["assets/fonts/" + name], "font")
    if include_source:
        yield book.emit(source_href, encoded(LOADED_CAPSULE), "renderer-source")
    doc = result.get("documentation")
    yield book.emit("model/documentation.json", encoded(doc), "original-documentation")
    details = {}
    for key, topic in (doc or {}).get("topics", {}).items():
        stem = "reference-" + digest(key)[:16]
        value = {
            name: topic[name]
            for name in (
                "id",
                "version",
                "fixture_id",
                "assumptions",
                "defaults",
                "contracts",
                "bindings",
                "review_status",
                "evidence",
            )
            if name in topic
        }
        yield from book.tables(
            stem,
            topic["title"] + " · original reference",
            value,
            "Original saved parameter defaults, component interfaces and scoped evidence. Current metadata has not been substituted.",
            "model/documentation.json",
        )
        details[key] = link(
            "model-report.html",
            "model/" + stem + "-1.html",
            "Parameter defaults, interfaces and evidence details",
        )
    examples = []
    for key, example in result.get("learning_examples", {}).items():
        name = "model/example-" + digest(key)[:16] + ".json"
        yield book.emit(name, encoded(example), "saved-example")
        values = (
            (m["label"], str(m["value"]) + " " + m["unit"]) for m in example.get("metrics", [])
        )
        examples.append(
            "<section><h3>"
            + html.escape(key)
            + " · saved learning output</h3><p>"
            + html.escape(example.get("summary", ""))
            + "</p>"
            + table("".join(table_chunks(values)))
            + "<p>"
            + link("model-report.html", name, "Saved inputs, trajectories and checks")
            + "</p></section>"
        )
    index = []
    for controller, records in result["records"].items():
        controller_id = digest(controller)[:16]
        for hour, record in enumerate(records):
            links = []
            context = dict(
                version=VERSION,
                controller=controller,
                interval=hour,
                time=record["time"],
                original_source=result.get("provenance", {}).get("source", {}).get("content_hash"),
                original_dispatch_prices=result.get("decision_cost_version"),
                original_service_prices=result.get("service_cost_version"),
                report_renderer_source=LOADED_SOURCE["content_hash"],
                decision_solver=record["decision"]["plan"].get("solver"),
            )
            for topic in TOPICS:
                value = calculation(result, topic, controller, hour)
                # Rendering retains prediction operands; kernel evidence is kept
                # in the linked complete recording instead of repeated per row.
                displayed = value
                if topic == "controllers":
                    displayed = {
                        **value,
                        "solver": record["decision"]["plan"].get("solver"),
                        "trajectory": [
                            {"offset": i, "applied": step["applied"], "ending": step["state"]}
                            for i, step in enumerate(value.get("trajectory", []))
                        ],
                    }
                stem = f"{controller_id}-h{hour:04d}-{topic}"
                data = "model/" + stem + ".json"
                yield book.emit(
                    data,
                    encoded({**context, "topic": topic, "calculation": value}),
                    "calculation-data",
                )
                note = "Retrospective execution calculation for this interval; not empirical plant validation."
                if topic in ("economics", "experiments"):
                    note = f"Accumulated report over intervals 0 through {hour}. Original dispatch assumptions remain frozen; the calculation identifies its reporting implementation."
                elif topic in ("controllers", "weather"):
                    note = "Prediction and information recorded at this decision boundary. Future realised weather is not substituted."
                elif topic == "diagnosis":
                    note = "Recorded sensor channels after the interval, and estimates before and after it. Availability follows the recorded interval boundary."
                yield from book.tables(
                    stem, f"{topic.title()} · {controller} · interval {hour}", displayed, note, data
                )
                links.append(link("model-report.html", "model/" + stem + "-1.html", topic.title()))
            if "field_operations" in record:
                field = record["field_operations"]
                stem = f"{controller_id}-h{hour:04d}-services"
                data = "model/" + stem + ".json"
                yield book.emit(
                    data, encoded({**context, "field_operations": field}), "service-data"
                )
                visible = {
                    k: v for k, v in field.items() if k not in ("decision", "planning_snapshot")
                }
                note = "Recorded service accounting, work state and events for this interval. Applied effects are retrospective; completion is distinct from diagnostic confirmation. The complete original decision search and planning snapshot are in the linked data."
                yield from book.tables(
                    stem, f"Service work · {controller} · interval {hour}", visible, note, data
                )
                links.append(link("model-report.html", "model/" + stem + "-1.html", "Service work"))
            index.append(
                "<tr><td>"
                + html.escape(controller)
                + "</td><td>"
                + str(hour)
                + "</td><td>"
                + html.escape(record["time"])
                + "</td><td>"
                + " · ".join(links)
                + "</td></tr>"
            )
    body = (
        '<p><a href="#calculations">Recorded calculations by interval</a> · <a href="#examples">Saved learning outputs</a></p>'
        + "<p>Read-only model snapshot and recorded calculations. These pages use the identified reading and calculation implementation; original explanations, actions and evidence remain as recorded. Live learning and replanning require the restored application. No simulation or learning fixture is run when producing these reading pages.</p><p>"
        + link(
            "model-report.html",
            "model/documentation.json",
            "Complete original explanations and scoped evidence",
        )
        + " · "
        + link("model-report.html", source_href, "Reading and calculation source")
        + "</p>"
    )
    body += (
        original_reference(doc, details)
        + '<h2 id="examples">Saved example outputs</h2>'
        + (
            "".join(examples)
            or "<p>No saved learning outputs are available. None have been reconstructed as original evidence.</p>"
        )
    )
    body += (
        '<h2 id="calculations">Recorded calculations</h2><p>Select a topic at its recorded interval. Observations, estimates, predictions and retrospective execution are labelled on the selected page. Blank or undefined costs do not mean zero.</p><div class="table-scroll" tabindex="0" aria-label="Recorded interval index"><table class="index-table"><thead><tr><th>Controller</th><th>Interval</th><th>Recorded time</th><th>Read calculations</th></tr></thead><tbody>'
        + "".join(index)
        + "</tbody></table></div>"
    )
    yield book.emit(
        "model-report.html", book.page("model-report.html", "Saved model report", body), "index"
    )
    manifest = dict(
        version=VERSION,
        run_id=result["run_id"],
        original_recording_integrity=result.get("integrity_sha256"),
        rendered_input_hash=digest(result),
        original_source=result.get("provenance", {}).get("source", {}).get("content_hash"),
        original_documentation_source=doc.get("source") if doc else None,
        renderer_source=LOADED_SOURCE["content_hash"],
        renderer_source_capsule_sha256=LOADED_CAPSULE["sha256"],
        source_href=source_href,
        archive_href=archive_href,
        files=book.files,
        scope="Derived reading pages of this recording. Current calculation/reading source is identified separately from original execution and explanations. Hashes establish integrity, not authenticity or empirical validation.",
    )
    yield "model/manifest.json", encoded(manifest)


def write(result, directory, *, archive_href):
    """Write to a new example directory; do not replace existing report pages."""
    root = Path(directory)
    for name, content in pages(result, archive_href=archive_href):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)
