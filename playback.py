"""Browser-local playback of the same causal hourly traces used by analysis/exports."""

from pathlib import Path

import gradio as gr

from economics import Costs, cost_timeline, physical_id

ASSETS = Path(__file__).resolve().parent / "assets"


def build_playback(result):
    return gr.HTML(
        playback_value(result),
        economics=cost_timeline(result, Costs()),
        html_template=(ASSETS / "playback.html")
        .read_text()
        .replace("<!-- PLANT SCENE -->", (ASSETS / "plant-scene.html").read_text()),
        css_template=(ASSETS / "playback.css").read_text()
        + (ASSETS / "plant-scene.css").read_text(),
        js_on_load=(ASSETS / "plant-scene.js").read_text()
        + (ASSETS / "plant-inspector.js").read_text()
        + (ASSETS / "playback.js").read_text()
        + "\nmountPlayback(element, props, watch);",
        apply_default_css=False,
        elem_id="playback",
    )


def playback_value(result):
    return {**result, "run_id": physical_id(result)}
