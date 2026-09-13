"""Shared Departure Mono instrument palette, served without remote font requests."""

import base64
from pathlib import Path

import gradio as gr

ASSETS = Path(__file__).resolve().parent / "assets"
AMBER, COMPARISON, INK, GRID, BACKGROUND = "#ffa32d", "#ddd1bc", "#dfc9a9", "#403729", "#202020"
FONT = "Departure Mono, monospace"
FONT_CSS = (
    "@font-face {font-family:'Departure Mono';font-style:normal;font-weight:400;"
    "font-display:swap;src:url(data:font/woff2;base64,"
    + base64.b64encode((ASSETS / "fonts/DepartureMono-Regular.woff2").read_bytes()).decode()
    + ") format('woff2');}"
)
CSS = FONT_CSS + (ASSETS / "app.css").read_text() + (ASSETS / "plant-motion.css").read_text()
HTML_CSS = (ASSETS / "summary.css").read_text()


def make_theme():
    return gr.themes.Base(
        primary_hue="orange",
        secondary_hue="orange",
        neutral_hue="stone",
        font=["Departure Mono", "monospace"],
        font_mono=["Departure Mono", "monospace"],
        radius_size=gr.themes.sizes.radius_none,
    ).set(
        body_background_fill=BACKGROUND,
        body_background_fill_dark=BACKGROUND,
        body_text_color=INK,
        body_text_color_dark=INK,
        body_text_color_subdued="#b5a184",
        body_text_color_subdued_dark="#b5a184",
        background_fill_primary=BACKGROUND,
        background_fill_primary_dark=BACKGROUND,
        background_fill_secondary="#28241f",
        background_fill_secondary_dark="#28241f",
        block_background_fill=BACKGROUND,
        block_background_fill_dark=BACKGROUND,
        block_border_color="#685032",
        block_border_color_dark="#685032",
        block_label_text_color=INK,
        block_label_text_color_dark=INK,
        block_title_text_color=AMBER,
        block_title_text_color_dark=AMBER,
        input_background_fill="#27231e",
        input_background_fill_dark="#27231e",
        input_border_color="#685032",
        input_border_color_dark="#685032",
        input_shadow="none",
        input_shadow_dark="none",
        border_color_primary="#685032",
        border_color_primary_dark="#685032",
        button_primary_background_fill=AMBER,
        button_primary_background_fill_dark=AMBER,
        button_primary_text_color=BACKGROUND,
        button_primary_text_color_dark=BACKGROUND,
        button_secondary_background_fill="#29251f",
        button_secondary_background_fill_dark="#29251f",
        button_secondary_text_color=AMBER,
        button_secondary_text_color_dark=AMBER,
        slider_color=AMBER,
        slider_color_dark=AMBER,
    )
