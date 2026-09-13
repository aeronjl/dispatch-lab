"""The rendered scene configuration cannot retain the server's state graph."""

from functools import partial

from methane.evidence import load
from methane.ui import build_app


def test_scene_constructor_inputs_are_data_not_a_bound_custom_event():
    app = build_app(load("tests/fixtures/browser-demo-v2.json.gz"))
    scene = next(
        c for c in app.config["components"] if c["props"].get("elem_id") == "methane-playback"
    )
    assert scene["props"].get("inputs") is None
    assert not isinstance(scene["props"].get("inputs"), partial)
    # Normal custom events remain registered and the component still embeds
    # the original illustration and playback behaviour.
    assert any(d["targets"] for d in app.config["dependencies"])
    assert "mountMethane" in scene["props"]["js_on_load"]
    assert "solar-component" in scene["props"]["html_template"]
