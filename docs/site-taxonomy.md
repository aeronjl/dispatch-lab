# Site taxonomy and component exploration

The taxonomy is an organising layer over the existing simulation and service contracts. It does not schedule work, grant a repair capability, introduce a new physical mechanism or reprice a run. The broader field-operations research programme remains paused.

## User workflow

Open **Explore component** in a component inspector, the solar workspace’s Model and evidence area, or **Explore service system** in the service view. **Explore plant** is also available in the simulation menu. The existing illustrated overview and its labels are preserved.

The explorer offers five views:

- **Inside**: constituent objects and service interfaces.
- **Operation**: existing observations and applied actions for plant equipment, decision-time public service information for mobile actors, or explicitly retrospective service receipts. Objects without a bound display say so.
- **Dependencies**: electricity and material connections, required observations, access points, tools and shared resources.
- **Service**: candidate actions, interfaces and family membership. Follow an interface to a capability, then an actor and its prerequisites. A compatible action is not an authorization or successful repair.
- **Model & evidence**: identities, bound parameters, assumptions, sources, scoped feasibility reviews and links to existing model essays and recorded calculations.

Selecting related objects keeps a navigation history. Escape/Return restores the originating screen and focus; entering pauses playback and leaves the selected controller and hour intact. Browse provides search and optional domain filters. Future concepts are excluded from search until requested. The twelve domains do not become twelve main-menu items.

## Vocabulary

The generated [reference](site-taxonomy.json) contains twelve domains: electrical energy; chemical production and materials; process utilities; instrumentation/actuation/protection; field machines; shared service infrastructure/logistics; inventories/flows/reservations; people/external services; site/environment; autonomy/information; economics/objectives/obligations; simulation/experiments/evidence.

Kind and domain are independent. An actor, stock, capacity, interface, observation or policy retains its own contract and behaviour. Faults, operating states, work orders and events are records rather than equipment families. Future concepts have no execution permissions, capacity, reliability or price.

Relationships include contains, powers, feeds, observes, services, depends on, requires, implements, member of, has interface, offers, compatible with, located at, connects, documents, configures, records and accounted by. `contains` is acyclic; process/electricity dependency cycles are valid. Service tools are declared compatibility types, not invented shared tool inventories.

Existing plant and service asset IDs are preserved. Other service IDs keep `original_id` and receive a namespace in graph IDs so an asset and a capacity slot cannot collide. Shared stocks retain one graph identity. Plant inventory nodes refer to component balances; they are not a second stock to sum into the ledger.

## Generation and coverage

`methane.taxonomy.build` adapts component specifications, explicit recorded configuration, execution identities, saved forecast identities, controller names, and every asset/interface/capability/resource/access edge in the recorded service registry. Requirements and resource quantities become explicit links. Additional registry entries receive coverage without teaching the UI about their particular family.

The 14 researched hardware families retain their original IDs. `docs/taxonomy-families.json` copies the reviewed capability boundaries and sources into the captured source bundle. A match between review and execution source is explicit; a different source does not inherit validation. Commercial feasibility, numerical verification and field validation remain separate.

The graph also names necessary concepts that are outside the present model. Naming compression, independent protection, product certification or learned-policy training does not implement it. Unrecorded legacy service contracts remain unavailable rather than acquiring modern capabilities from an asset label.

## Preservation and transport

New runs contain one `taxonomy` snapshot with schema `dispatch-lab/site-taxonomy/1`, source identities and a content digest. It is sealed with the run. Existing archive column meanings and physical records are unchanged.

**This run** uses that snapshot. Older archives report a missing original catalogue. **Current catalogue** is explicitly a current interpretation of the selected archive’s recorded configuration, not a reconstruction of original evidence. Parameter values come from recorded configuration or execution operands. Missing bindings remain unavailable; reference defaults are not presented as original inputs.

The read-only `/dispatch/taxonomy` endpoint resolves the existing server-owned run token and returns the request generation and run ID. The UI aborts obsolete requests and rejects late or mismatched responses. Navigation operates locally after loading the graph; numerical calculations stay in the existing model/trace workflows.

Reproduction bundles include `site-catalogue.html` and, for new runs, `site-catalogue.json`. The human-readable report preserves original relationships, definitions, assumptions and sources offline. New-source playback includes the explorer with the recorded snapshot. External references remain links. Old bundles retain their original playback behaviour and explicitly report missing original catalogue metadata.

## Checks

Run `python -m methane.taxonomy generate` after an intentional vocabulary or family-review change, and `python -m methane.taxonomy check` to detect stale generated references. This gate checks reference freshness, not scientific realism.

`tests/test_taxonomy.py` checks registry coverage, all domains/families, identity collisions, relationship resolution, acyclic containment, shared resources, unsupported capabilities, snapshot immutability, legacy archives, source applicability, token binding and offline reports. Browser tests exercise navigation, return focus, nested Model access, source links, search, narrow screens and late-response handling. Existing plant/solar screenshots remain the visual preservation gate.
