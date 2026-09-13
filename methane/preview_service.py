"""Small read-only preview transport on Gradio's FastAPI app.

The normal component update path reconstructs the large HTML component. A
capability token instead addresses a bounded, frozen weather/design input. No
dispatch, file access, or source-run mutation is exposed by this endpoint.
"""

import copy
import secrets
from collections import OrderedDict
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import HTTPException
from pydantic import BaseModel, Field

from methane.solar import preview, source_config, source_weather

_inputs = OrderedDict()
_lock = Lock()


class PreviewRequest(BaseModel):
    token: str = Field(max_length=100)
    run_id: str = Field(max_length=100)
    key: str = Field(max_length=250)
    design: dict


def register(result):
    # The store owns only the necessary immutable reference; no plans or raw responses.
    frozen = copy.deepcopy(
        {
            "run_id": result["run_id"],
            "config": result["config"],
            "weather": {
                "times": result["weather"]["times"],
                "truth": result["weather"]["truth"],
                "solar_reference_weather": {"truth": source_weather(result)["truth"]},
                "solar_reference_config": source_config(result).to_dict(),
            },
        }
    )
    token = secrets.token_urlsafe(32)
    with _lock:
        _inputs[token] = frozen
        while len(_inputs) > 16:
            _inputs.popitem(last=False)
    return token


def calculate(request: PreviewRequest):
    with _lock:
        source = _inputs.get(request.token)
        if source is None or source["run_id"] != request.run_id:
            raise HTTPException(410, "Preview context expired; reload the saved run.")
        _inputs.move_to_end(request.token)
    try:
        return {**preview(source, request.design), "key": request.key}
    except (ValueError, KeyError, TypeError) as exc:
        return {"key": request.key, "error": str(exc)}


@asynccontextmanager
async def lifespan(app):
    app.add_api_route("/dispatch/preview-solar", calculate, methods=["POST"])
    from methane.taxonomy_service import document as taxonomy_document

    app.add_api_route("/dispatch/taxonomy", taxonomy_document, methods=["POST"])
    from methane.model_service import document, example, job

    app.add_api_route("/dispatch/model-document", document, methods=["POST"])
    app.add_api_route("/dispatch/learning-example", example, methods=["POST"])
    app.add_api_route("/dispatch/learning-job", job, methods=["POST"])
    from methane.service_alternatives_service import cleanup
    from methane.service_alternatives_service import handle as service_alternative

    app.add_api_route("/dispatch/service-alternative", service_alternative, methods=["POST"])
    from methane.study_service import download, handle

    app.add_api_route("/dispatch/studies", handle, methods=["POST"])
    app.add_api_route("/dispatch/study-download/{edition_id}", download, methods=["GET"])
    try:
        yield
    finally:
        cleanup()
