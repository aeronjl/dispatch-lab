"""Use a fixed, pre-refactor archived run: browser assertions never depend on a solver."""

import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# Study UI checks use disposable, actually executed short cases; never user studies.
(ROOT / "build").mkdir(exist_ok=True)
os.environ["DISPATCH_STUDY_STORE"] = tempfile.mkdtemp(prefix="browser-studies-", dir=ROOT / "build")
os.environ["DISPATCH_SITES_ROOT"] = tempfile.mkdtemp(prefix="browser-sites-", dir=ROOT / "build")
from app import CSS, make_theme  # noqa: E402
from methane import studies  # noqa: E402
from methane.evidence import load  # noqa: E402
from methane.preview_service import lifespan  # noqa: E402
from methane.startup import launch_local  # noqa: E402
from methane.ui import build_app  # noqa: E402
from ui_theme import ASSETS  # noqa: E402

original_protocol = studies.protocol
small_study = original_protocol()
small_study["tiers"]["reference"].update(hours=6, seeds=[42], solver_seconds=0.05)
small_study["tiers"]["smoke"].update(hours=2, seeds=[42], battery_factors=[1], solver_seconds=0.05)
small_study["review"]["scope"] = "Short browser integration fixture, not research evidence."
studies.protocol = lambda: small_study
study = studies.create(tier="reference")
studies.run_edition(study["edition_id"])
studies.protocol = original_protocol

if os.environ.get("DISPATCH_FIELD_STUDIES"):
    field_protocol = original_protocol("field-recovery")
    field_protocol["conditions"] = [field_protocol["conditions"][2]]
    for tier in field_protocol["tiers"].values():
        tier.update(hours=18, horizon_hours=6, seeds=[7], solver_seconds=0.05)
        tier["variants"] = tier["variants"][:1]
        tier["purpose"] = "Browser integration fixture; not comparative research evidence."
    field_protocol["review"]["scope"] = "Short browser integration fixture, not research evidence."
    studies.protocol = lambda identifier=None: (
        field_protocol if identifier == "field-recovery" else original_protocol(identifier)
    )
    field_edition = studies.create(protocol_id="field-recovery", tier="reference")
    studies.run_edition(field_edition["edition_id"])

if os.environ.get("DISPATCH_COMPUTATION_STUDIES"):
    computation_protocol = original_protocol("field-computation")
    computation_protocol["conditions"] = computation_protocol["conditions"][:1]
    for tier in computation_protocol["tiers"].values():
        tier.update(hours=2, seeds=[7])
        tier["variants"] = tier["variants"][:1]
        tier["computation"]["repetitions"] = 2
        tier["computation"]["budgets"] = tier["computation"]["budgets"][:1]
        tier["purpose"] = "Short browser integration fixture; not research evidence."
    studies.protocol = lambda identifier=None: (
        computation_protocol if identifier == "field-computation" else original_protocol(identifier)
    )
    computation_edition = studies.create(protocol_id="field-computation", tier="reference")
    studies.run_edition(computation_edition["edition_id"])

fixture = load(
    os.environ.get("DISPATCH_BROWSER_ARCHIVE", ROOT / "tests/fixtures/browser-demo-v2.json.gz")
)
if os.environ.get("DISPATCH_BROWSER_HOURS") and not os.environ.get("DISPATCH_BROWSER_ARCHIVE"):
    from methane.config import Config
    from methane.simulation import run

    config = Config()
    config = replace(
        config, scenario=replace(config.scenario, hours=int(os.environ["DISPATCH_BROWSER_HOURS"]))
    )
    fixture = run(config, strategies=("Greedy",))

launch_local(
    build_app(fixture).queue(max_size=8),
    app_kwargs={"lifespan": lifespan},
    server_name="127.0.0.1",
    server_port=7861,
    share=False,
    theme=make_theme(),
    css=CSS + (ASSETS / "methane-motion.css").read_text(),
    js="document.body.classList.add('dark');",
    footer_links=[],
    allowed_paths=[str(ROOT / "docs/components.md")],
)
