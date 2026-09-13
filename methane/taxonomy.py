"""Read-only site graph, derived from existing contracts and recorded service manifests.

The graph organises identities, not execution. A compatible action is a declared
candidate; it is never a grant of access, evidence, resources or repair authority.
"""

import argparse
import copy
import hashlib
import html
import json
from pathlib import Path

from methane.taxonomy_definitions import (
    CONCEPTS,
    CORE,
    DEPTHS,
    DOMAINS,
    KINDS,
    RELATIONS,
    SYSTEMS,
    VERSION,
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def family_review():
    from methane.provenance import LOADED_FILES

    return json.loads(LOADED_FILES["docs/taxonomy-families.json"])


def build(result):
    """Current interpretation of recorded configuration; snapshots call this once at sealing."""
    from methane.contracts import SPECS
    from methane.provenance import LOADED_SOURCE

    nodes, edges, aliases = {}, [], {"site": "PLANT-01"}
    config = result.get("config", {})
    assets = {"site": "PLANT-01", **result.get("asset_ids", {})}
    source = result.get("provenance", {}).get("source", {}).get("content_hash")
    first_row = next((rows[0] for rows in result.get("records", {}).values() if rows), {})

    def add(key, label, domain, kind, depth="declared", **extra):
        if key in nodes:
            return key
        nodes[key] = dict(
            id=key, label=label, domain=domain, kind=kind, depth=depth, status="reference", **extra
        )
        return key

    def link(a, relation, b, note=""):
        edge = dict(source=a, relation=relation, target=b, note=note)
        if edge not in edges:
            edges.append(edge)

    site = add(assets["site"], "Plant and support system", "environment", "site", "implemented")
    aliases["site"] = site
    for name, (label, domain) in CORE.items():
        key = assets.get(name, "component:" + name)
        aliases[name] = key
        spec = SPECS[name].to_dict()
        execution = first_row.get("component_records", {}).get(name, {})
        if name == "battery":
            execution = first_row.get("battery_record", execution)
        execution_parameters = execution.get("parameters", {})
        # Snapshot documentation is authoritative for archived scientific explanations.
        key = add(
            key,
            label,
            domain,
            "asset",
            "implemented",
            topic=name,
            summary="Reduced hourly model. Explore its contracts and applicable evidence.",
            parameters=[
                {
                    **p,
                    "value": config.get("plant", {}).get(
                        p["key"], execution_parameters.get(p["key"])
                    ),
                }
                for p in spec["parameters"]
            ],
            assumptions=spec["assumptions"],
            sources=spec["references"],
            implementation=execution.get("implementation_id", config.get("models", {}).get(name)),
            metadata={
                **{k: v for k, v in spec.items() if k != "parameters"},
                "execution_identity": {
                    k: execution[k]
                    for k in ("model_id", "model_version", "implementation_id")
                    if k in execution
                },
                "execution_parameters": execution_parameters,
                "parameter_boundary": "Values bind to recorded configuration or execution operands. A null value is unavailable; default is reference metadata only.",
            },
        )
        nodes[key]["status"] = "configured"
        link(site, "contains", key)
        model = add(
            "model:" + name,
            execution.get("model_id", spec["model_id"]),
            "evidence",
            "model",
            "implemented",
            topic=name,
            metadata=nodes[key]["metadata"],
        )
        link(key, "implements", model)
    for name, (label, domain, summary) in SYSTEMS.items():
        aliases[name] = add(
            "system:" + name,
            label,
            domain,
            "system",
            "accounting" if name in ("water", "product") else "implemented",
            topic=name
            if name in ("bus", "weather", "diagnosis", "controllers", "economics", "experiments")
            else None,
            summary=summary,
        )
        link(site, "contains", aliases[name])
    for a, relation, b in [
        ("solar", "powers", "bus"),
        ("battery", "powers", "bus"),
        ("bus", "powers", "battery"),
        ("bus", "powers", "electrolyser"),
        ("bus", "powers", "thermal"),
        ("bus", "powers", "reactor"),
        ("bus", "powers", "services"),
        ("water", "feeds", "electrolyser"),
        ("electrolyser", "feeds", "hydrogen"),
        ("hydrogen", "feeds", "reactor"),
        ("co2", "feeds", "reactor"),
        ("reactor", "feeds", "product"),
        ("reactor", "feeds", "water"),
        ("reactor", "depends_on", "thermal"),
        ("sensors", "observes", "electrolyser"),
        ("sensors", "observes", "hydrogen"),
        ("diagnosis", "depends_on", "sensors"),
        ("controllers", "depends_on", "diagnosis"),
        ("controllers", "depends_on", "weather"),
        ("controllers", "depends_on", "economics"),
        ("solar", "depends_on", "weather"),
        ("thermal", "depends_on", "weather"),
        ("services", "depends_on", "diagnosis"),
    ]:
        link(aliases[a], relation, aliases[b])
    # Plant inventory nodes are references to existing balances, not duplicate stocks.
    for name, field, unit, owner in [
        ("Battery energy", "battery_kwh", "kWh", "battery"),
        ("Hydrogen inventory", "h2_kg", "kg", "hydrogen"),
        ("CO₂ inventory", "co2_kg", "kg", "co2"),
    ]:
        key = add(
            "inventory:" + field,
            name,
            "resources",
            "resource",
            "implemented",
            metadata={
                "state_field": field,
                "unit": unit,
                "ownership": "Reference to component balance; do not add to service stock",
            },
        )
        link(aliases[owner], "contains", key)
    # Every configuration block has one place, even when disabled or absent.
    for name, settings in config.items():
        domain = (
            "economics"
            if "cost" in name or "economics" in name
            else "environment"
            if name == "weather"
            else "evidence"
        )
        key = add(
            "configuration:" + name,
            name.replace("_", " ").capitalize(),
            domain,
            "configuration",
            "declared",
            metadata=settings,
            summary="Recorded configuration. Null means this optional configuration was not supplied.",
        )
        owner = (
            "weather"
            if name == "weather"
            else "economics"
            if domain == "economics"
            else "experiments"
        )
        link(key, "configures", aliases[owner])
        link(aliases[owner], "contains", key)
    solar = config.get("solar") or {}
    for i, section in enumerate(solar.get("sections", [])):
        key = add(
            f"{aliases['solar']}/section/{i}",
            section.get("name", f"Section {i + 1}"),
            "electrical",
            "asset",
            "implemented",
            topic="solar",
            metadata=section,
        )
        nodes[key]["status"] = "configured"
        link(aliases["solar"], "contains", key)
    review = family_review()
    for f in review["families"]:
        domain = (
            "instrumentation"
            if f["id"] in ("fixed-sensor", "sampler", "calibration", "remote-actuator")
            else "electrical"
            if f["id"] == "deployable-array"
            else "field"
        )
        key = add(
            "family:" + f["id"],
            f["name"],
            domain,
            "family",
            "declared",
            summary=f["permitted_scope"],
            metadata=f,
            boundary=f["unavailable_scope"],
            sources=f["sources"],
            evidence_scope="Feasibility review, not permission to execute or empirical validation.",
            review_applies_to_execution=source == review["reviewed_execution_source"],
        )
        link(aliases["services"], "documents", key)
    manifest = result.get("field_operations_model") or {}
    definitions = manifest.get("definitions") or {}
    has_registry = bool(definitions)
    nodes[aliases["services"]]["metadata"] = {
        k: v for k, v in manifest.items() if k != "definitions"
    }
    nodes[aliases["services"]]["depth"] = "implemented" if manifest else "unavailable"
    nodes[aliases["services"]]["summary"] += (
        ". Recorded registry available."
        if has_registry
        else ". Original service registry unavailable; no capabilities inferred from hardware names."
    )
    coverage = {}
    group_specs = {
        "assets": ("asset_id", "asset", "field"),
        "interfaces": ("interface_id", "interface", "instrumentation"),
        "capabilities": ("capability_id", "capability", "field"),
        "resources": ("resource_id", "resource", "resources"),
        "access": ("edge_id", "route", "environment"),
    }
    index = {}
    for group, (id_field, kind, domain) in group_specs.items():
        coverage[group] = []
        for item in definitions.get(group, []):
            original = item[id_field]
            key = original if group == "assets" else group + ":" + original
            index[(group, original)] = key
            coverage[group].append(original)
            label = next(
                (k.replace("_", " ").capitalize() for k, v in assets.items() if v == original),
                original,
            )
            actual_kind = "actor" if item.get("autonomy") == "human" else kind
            actual_domain = "people" if actual_kind == "actor" else domain
            if item.get("mobility") == "fixed" and actual_kind == "asset":
                actual_domain = (
                    "instrumentation"
                    if item.get("archetype") in ("fixed-sensor", "remote-actuator")
                    else "support"
                )
            add(
                key,
                label,
                actual_domain,
                actual_kind,
                "implemented",
                original_id=original,
                metadata=item,
                sources=item.get("sources", []),
                implementation=item.get("implementation_id"),
                summary="Recorded service contract. Requirements and verification still govern each attempt.",
            )
            nodes[key]["status"] = "configured"
            link(aliases["services"], "contains", key)
    for name, descriptor in manifest.items():
        if name in ("definitions", "source", "asset_ids") or not isinstance(descriptor, dict):
            continue
        kind = "model" if "implementation_id" in descriptor else "configuration"
        key = add(
            "service-definition:" + name,
            name.replace("_", " ").capitalize(),
            "evidence",
            kind,
            "declared",
            metadata=descriptor,
            implementation=descriptor.get("implementation_id"),
            summary="Recorded service-system definition; nested fields retain their original meaning.",
        )
        link(aliases["services"], "implements" if kind == "model" else "configures", key)
    # Older manifests keep their original asset identities, but never receive modern capabilities.
    for name, original in assets.items():
        if original not in nodes:
            add(
                original,
                name.replace("_", " ").capitalize(),
                "support",
                "asset",
                "unavailable",
                summary="Recorded identity only. Original detailed contract is unavailable.",
            )
            link(aliases["services"], "contains", original)
        aliases.setdefault(name, original)

    def related(group, original):
        # A broken registry must fail rather than silently creating a valid-looking resource.
        try:
            return index[(group, original)]
        except KeyError as exc:
            raise ValueError(f"Unresolved service reference: {group}/{original}") from exc

    def place(name):
        return add(
            "place:" + name,
            name.capitalize(),
            "environment",
            "place",
            summary="Declared access point; not a surveyed coordinate or geometric route.",
        )

    def tool(name):
        return add(
            "tool:" + name,
            name,
            "support",
            "tool",
            summary="Declared tool compatibility; no implied possession by other assets.",
        )

    def requirements(key, item):
        for req in [*item.get("requirements", []), *item.get("acceptance", [])]:
            channel = add(
                "channel:" + req["channel"],
                req["channel"],
                "instrumentation",
                "observation",
                metadata={"unit": req["unit"]},
                summary="An observation requirement, not evidence that it is currently satisfied.",
            )
            link(key, "requires", channel, json.dumps(req, sort_keys=True))
        for field in ("consumables", "hourly_consumables", "shared_resources", "support_resources"):
            for quantity in item.get(field, []):
                link(
                    key,
                    "depends_on",
                    related("resources", quantity["resource"]),
                    field + ": " + json.dumps(quantity, sort_keys=True),
                )

    for item in definitions.get("assets", []):
        key = item["asset_id"]
        family = "family:" + item["archetype"]
        if family not in nodes:
            add(
                family,
                item["archetype"],
                "support",
                "family",
                summary="Implementation family; no independent feasibility review recorded.",
            )
        link(key, "member_of", family)
        link(key, "located_at", place(item["home"]))
        for cap in item["capabilities"]:
            link(key, "offers", related("capabilities", cap))
        for name in item.get("tools", []):
            link(
                key,
                "requires",
                tool(name),
                "Declared tool type; not a shared physical tool inventory.",
            )
        if item.get("battery_resource"):
            link(key, "depends_on", related("resources", item["battery_resource"]))
        requirements(key, item)
    for item in definitions.get("interfaces", []):
        key = related("interfaces", item["interface_id"])
        target = item["target_asset_id"]
        if target not in nodes:
            add(
                target,
                target,
                "process",
                "asset",
                "declared",
                summary="Target declared by service interface; no separate physical kernel.",
            )
            link(site, "contains", target)
        link(target, "has_interface", key)
        link(key, "located_at", place(item["point"]))
        for name in item.get("required_tools", []):
            link(key, "requires", tool(name))
        for resource in item.get("exclusive_resources", []):
            link(key, "depends_on", related("resources", resource))
        requirements(key, item)
        for cap in definitions.get("capabilities", []):
            if cap["action"] in item["actions"]:
                cap_key = related("capabilities", cap["capability_id"])
                link(
                    cap_key,
                    "compatible_with",
                    key,
                    "Action match only; tools, access, observations, resources and acceptance must also pass.",
                )
                link(
                    cap_key,
                    "services",
                    target,
                    "Declared candidate, not a scheduled or successful repair.",
                )
    for item in definitions.get("capabilities", []):
        requirements(related("capabilities", item["capability_id"]), item)
    for item in definitions.get("access", []):
        key = related("access", item["edge_id"])
        link(key, "connects", place(item["origin"]))
        link(key, "connects", place(item["destination"]))
        if item.get("resource_id"):
            link(key, "depends_on", related("resources", item["resource_id"]))
        requirements(key, item)
    for name, rows in result.get("records", {}).items():
        policy = add(
            "policy:" + name,
            name,
            "autonomy",
            "policy",
            "implemented",
            topic="controllers",
            metadata={
                "controller": name,
                "original_decision_cost_version": result.get("decision_cost_version"),
                "recorded_decisions": len(rows),
            },
            summary="Recorded controller identity. Plans, observations and assumptions remain attached to each decision.",
        )
        link(aliases["controllers"], "contains", policy)
    for saved in result.get("weather", {}).get("snapshots", []):
        identity = saved.get("id")
        if identity:
            key = add(
                "forecast:" + identity,
                "Forecast " + identity,
                "autonomy",
                "evidence",
                "declared",
                topic="weather",
                metadata={k: v for k, v in saved.items() if not isinstance(v, (dict, list))},
                summary="Saved forecast identity. Its availability boundary still governs use at a decision.",
            )
            link(aliases["weather"], "records", key)
    # A disabled service model is not an installed service system.
    if not config.get("field_operations", {}).get("enabled", False):
        nodes[aliases["services"]]["status"] = "disabled"
    # State/lifecycle/events are records, never extra equipment families.
    for name, kind, label, note in [
        (
            "faults",
            "state",
            "Fault and degradation state",
            "Injected truth stays retrospective; persistent faults require an accepted repair.",
        ),
        (
            "observations",
            "observation",
            "Observations and estimates",
            "Availability and sensor quality govern information used by controllers.",
        ),
        (
            "work",
            "task",
            "Work orders and missions",
            "Requests, reservations, receipts and verification belong to the service ledger.",
        ),
        (
            "events",
            "event",
            "Operating events",
            "Starts, diagnoses, trips and recovery are time-stamped records.",
        ),
        (
            "evidence",
            "evidence",
            "Model evidence",
            "Scoped numerical checks and sources; no overall trust score or implied plant calibration.",
        ),
    ]:
        key = add(
            "records:" + name,
            label,
            "evidence",
            kind,
            "implemented",
            summary=note,
            topic="diagnosis" if name == "observations" else "experiments",
        )
        link(aliases["experiments"], "records", key)
    for domain, labels in CONCEPTS.items():
        for label in labels:
            key = add(
                "concept:" + label.lower().replace(" ", "-"),
                label,
                domain,
                "concept",
                "concept",
                summary="Future catalogue concept. No execution capability, reliability, capacity or cost is assumed.",
            )
            link(site, "documents", key)
    for item in list(nodes.values()):
        if item["kind"] in ("asset", "actor", "resource", "capability") and item["depth"] in (
            "implemented",
            "accounting",
        ):
            link(
                item["id"],
                "accounted_by",
                aliases["economics"],
                "Cost attribution is in the recorded cost report; this link does not imply that every quantity has a price.",
            )
    graph = dict(
        schema_version=VERSION,
        catalogue_source=LOADED_SOURCE["content_hash"],
        execution_source=source,
        domains=DOMAINS,
        nodes=list(nodes.values()),
        edges=edges,
        aliases=aliases,
        coverage=coverage,
        family_review=review,
        scope="Organising metadata. Relationships do not authorize actions or prove feasibility.",
    )
    from methane.assumptions import snapshot as assumption_snapshot

    graph["assumption_review"] = assumption_snapshot(config)
    graph["uncertainty"] = copy.deepcopy(result.get("uncertainty"))
    graph["content_hash"] = digest(graph)
    validate(graph)
    return graph


def validate(graph):
    nodes = {n["id"]: n for n in graph["nodes"]}
    if len(nodes) != len(graph["nodes"]):
        raise ValueError("Duplicate taxonomy identity")
    children = {}
    for node in nodes.values():
        if (
            node["domain"] not in DOMAINS
            or node["kind"] not in KINDS
            or node["depth"] not in DEPTHS
        ):
            raise ValueError("Unknown taxonomy vocabulary")
    for edge in graph["edges"]:
        if (
            edge["source"] not in nodes
            or edge["target"] not in nodes
            or edge["relation"] not in RELATIONS
        ):
            raise ValueError("Unresolved taxonomy relationship")
        if edge["relation"] == "contains":
            children.setdefault(edge["source"], []).append(edge["target"])

    def visit(key, path):
        if key in path:
            raise ValueError("Cyclic containment")
        for child in children.get(key, []):
            visit(child, path | {key})

    for key in nodes:
        visit(key, set())
    if any(key not in nodes for key in graph["aliases"].values()):
        raise ValueError("Unresolved taxonomy alias")
    if graph.get("content_hash") != digest({k: v for k, v in graph.items() if k != "content_hash"}):
        raise ValueError("Taxonomy snapshot content changed")


def snapshot(result):
    return copy.deepcopy(build(result))


def response(result, context="This run"):
    if context not in ("This run", "Current catalogue"):
        raise ValueError("Unknown catalogue context")
    if context == "This run":
        graph = result.get("taxonomy")
        if graph:
            validate(graph)
        return dict(
            context=context,
            graph=graph,
            note="Original catalogue captured with this run."
            if graph
            else "Original catalogue unavailable for this archive. Switch to Current catalogue for an explicitly current interpretation of its recorded setup.",
        )
    return dict(
        context=context,
        graph=build(result),
        note="Current catalogue interpreting this run’s recorded configuration. This is not its original documentation or new evidence of realism.",
    )


def report(result):
    payload = response(result)
    esc = html.escape
    if not payload["graph"]:
        return (
            '<!doctype html><meta charset="utf-8"><h1>Site catalogue</h1><p>'
            + esc(payload["note"])
            + "</p>"
        )
    g = payload["graph"]
    nodes = {n["id"]: n for n in g["nodes"]}
    body = []
    from methane.assumptions import report_html as assumption_html

    body.append(assumption_html(g.get("assumption_review")))
    from methane.uncertainty import report_html as uncertainty_html

    body.append(uncertainty_html(g.get("uncertainty")))
    for node in nodes.values():
        relations = "".join(
            f'<li>{esc(e["relation"].replace("_", " "))}: <a href="#{esc(e["target"], quote=True)}">{esc(nodes[e["target"]]["label"])}</a> {esc(e["note"])}</li>'
            for e in g["edges"]
            if e["source"] == node["id"]
        )
        body.append(
            f'<section id="{esc(node["id"], quote=True)}"><h2>{esc(node["label"])}</h2><p>{esc(node["id"])} · {esc(node["kind"])} · {esc(node["depth"])} · {esc(node["status"])}</p><p>{esc(node.get("summary", ""))}</p><p>{esc(node.get("boundary", ""))}</p><ul>{relations}</ul><pre>{esc(json.dumps(node, indent=2, ensure_ascii=False))}</pre></section>'
        )
    sources = g.get("family_review", {}).get("sources", {}).get("items", [])
    if sources:
        body.append('<section id="review-sources"><h2>Sources for family feasibility reviews</h2>')
        for item in sources:
            url = item.get("url", "")
            title = esc(item.get("title", item["id"]))
            label = (
                f'<a href="{esc(url, quote=True)}" rel="noopener noreferrer">{title}</a>'
                if url.startswith(("https://", "http://"))
                else title
            )
            body.append(
                f"<p><strong>{esc(item['id'])}</strong> · {label}</p><p>{esc(item.get('scope', ''))}</p>"
            )
        body.append("</section>")
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Recorded site catalogue</title><style>body{max-width:900px;margin:3em auto;padding:1em;background:#202020;color:#ffc078;font:16px/1.6 monospace}a{color:#ffa12d}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{border-top:1px solid #785735;margin-top:3em}h1,h2{font-weight:400}</style><h1>Recorded site catalogue</h1><p>'
        + esc(payload["note"])
        + "</p><p>"
        + esc(g["scope"])
        + "</p>"
        + "".join(body)
        + "</html>"
    )


def reference():
    return dict(
        schema_version=VERSION,
        domains=DOMAINS,
        kinds=sorted(KINDS),
        relationships=sorted(RELATIONS),
        depths=sorted(DEPTHS),
        core=CORE,
        systems=SYSTEMS,
        concepts=CONCEPTS,
        family_review_hash=digest(family_review()),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("generate", "check"))
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "docs/site-taxonomy.json"
    content = json.dumps(reference(), indent=2, ensure_ascii=False) + "\n"
    if args.operation == "generate":
        path.write_text(content)
    elif not path.exists() or path.read_text() != content:
        raise SystemExit("Taxonomy reference stale; review vocabulary and regenerate it.")
    print("Taxonomy reference is current.")


if __name__ == "__main__":
    main()
