"""Authored organising vocabulary. Descriptors never grant execution capabilities."""

VERSION = "dispatch-lab/site-taxonomy/1"
DOMAINS = {
    "electrical": "Electrical energy",
    "process": "Chemical production and material handling",
    "utilities": "Process utilities",
    "instrumentation": "Instrumentation, actuation and protection",
    "field": "Field-work machines",
    "support": "Service infrastructure and logistics",
    "resources": "Inventories, flows and reservable resources",
    "people": "People and external services",
    "environment": "Site and environment",
    "autonomy": "Autonomy and information",
    "economics": "Economics, objectives and obligations",
    "evidence": "Simulation, experiments and evidence",
}
# The overview has six familiar components. These domains are search filters, not menu tabs.
CORE = {
    "solar": ("Solar array", "electrical"),
    "battery": ("Battery", "electrical"),
    "electrolyser": ("Electrolyser", "process"),
    "hydrogen": ("Hydrogen buffer", "process"),
    "co2": ("CO₂ supply and buffer", "process"),
    "reactor": ("Methanator", "process"),
}
SYSTEMS = {
    "bus": ("Electrical bus", "electrical", "Hourly shared electricity balance"),
    "water": (
        "Process water",
        "utilities",
        "Consumption and production accounting; no recycling credit",
    ),
    "thermal": (
        "Reactor heating and cooling",
        "utilities",
        "Lumped hourly heat balance and cooling electricity",
    ),
    "product": (
        "Methane output",
        "process",
        "Produced mass; no gas certification or customer acceptance",
    ),
    "sensors": (
        "Plant sensors",
        "instrumentation",
        "Seeded observation channels, separate from simulator truth",
    ),
    "diagnosis": (
        "State estimation and diagnosis",
        "autonomy",
        "Bounded residual diagnosis and recovery probes",
    ),
    "controllers": (
        "Dispatch controllers",
        "autonomy",
        "Recorded policies, forecasts, objectives and feasible fallback",
    ),
    "weather": (
        "Weather and forecasts",
        "environment",
        "Saved forecasts and reference weather with availability boundaries",
    ),
    "services": (
        "Field service system",
        "support",
        "Configured service hardware and resources; capabilities depend on interfaces",
    ),
    "economics": (
        "Cost accounting and decision economics",
        "economics",
        "Separate period allocation, action costs and expenditure",
    ),
    "experiments": (
        "Experiments and reproduction",
        "evidence",
        "Matched cases, recorded runs, model identities and scoped checks",
    ),
}
# Concepts deliberately carry no capacity, rate, repair permission or price.
CONCEPTS = {
    "electrical": ["Electrical distribution and protection", "Critical power and UPS"],
    "process": [
        "Compression and pressure regulation",
        "Pipes, valves and pumps",
        "Gas purification and quality certification",
        "Product storage and delivery",
        "Direct-air capture",
    ],
    "utilities": [
        "Water treatment and recirculation",
        "Service gases",
        "Ventilation",
        "Waste and discharge handling",
    ],
    "instrumentation": [
        "Independent safety system",
        "Gas leak and fire protection",
        "Sampling and laboratory analysis",
    ],
    "support": [
        "Workshop and tools store",
        "Fleet retrieval and transport",
        "Communications infrastructure",
        "Site computing",
        "Replenishment logistics",
    ],
    "people": [
        "Remote operator",
        "Qualified service contractor",
        "Feedstock supplier",
        "Site owner and operator",
        "Product recipient",
    ],
    "environment": [
        "Site layout and access design",
        "Hazard and exclusion zones",
        "Planning and weather restrictions",
    ],
    "autonomy": ["Learned policy training", "Predictive maintenance and remaining useful life"],
    "economics": [
        "Contractual service levels",
        "Product acceptance obligations",
        "Ownership and settlement",
    ],
}
KINDS = {
    "site",
    "asset",
    "system",
    "resource",
    "actor",
    "interface",
    "capability",
    "route",
    "place",
    "tool",
    "observation",
    "model",
    "policy",
    "configuration",
    "family",
    "concept",
    "evidence",
    "state",
    "event",
    "task",
}
RELATIONS = {
    "accounted_by",
    "contains",
    "powers",
    "feeds",
    "observes",
    "services",
    "depends_on",
    "implements",
    "member_of",
    "has_interface",
    "offers",
    "compatible_with",
    "requires",
    "located_at",
    "connects",
    "documents",
    "configures",
    "records",
}
DEPTHS = {"implemented", "accounting", "declared", "concept", "unavailable"}
