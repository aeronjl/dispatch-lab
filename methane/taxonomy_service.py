"""Read-only catalogue transport; resolves the same immutable run as model inspection."""

from fastapi import HTTPException
from pydantic import BaseModel, Field

from methane.model_service import recorded_context
from methane.taxonomy import response


class Request(BaseModel):
    token: str = Field(max_length=100)
    run_id: str = Field(max_length=100)
    key: str = Field(max_length=250)
    context: str = "This run"


def document(request: Request):
    run = recorded_context(request.token, request.run_id)
    try:
        return {**response(run, request.context), "key": request.key, "run_id": request.run_id}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
