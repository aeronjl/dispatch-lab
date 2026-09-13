from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from methane import studies
from methane.config import Config
from methane.study_service import Request, download, handle, register


def test_download_uses_actual_preserved_export_path(tmp_path, monkeypatch):
    edition, report = "0" * 32, "1" * 32
    token = register({"run_id": "recording", "config": Config().to_dict()})
    monkeypatch.setattr(studies, "STORE", tmp_path)
    monkeypatch.setattr(studies, "read_manifest", lambda *a, **k: {})
    monkeypatch.setattr(studies, "stored_report", lambda *a, **k: {"report_id": report})
    monkeypatch.setattr(studies, "withdrawal", lambda *a, **k: None)

    def exporter(identifier, destination, **kwargs):
        path = destination.with_name(destination.stem + "-" + "a" * 64 + ".zip")
        path.write_bytes(b"export fixture")
        return path

    monkeypatch.setattr(studies, "export", exporter)
    answer = handle(
        Request(
            token=token, run_id="recording", key="export", operation="export", edition_id=edition
        )
    )
    query = parse_qs(urlparse(answer["download_url"]).query)
    artifact = query["artifact"][0]
    response = download(edition, token, report, artifact)
    assert response.path == tmp_path / artifact
    assert response.path.read_bytes() == b"export fixture"
    with pytest.raises(HTTPException) as error:
        download(edition, token, report, "../unrelated.zip")
    assert error.value.status_code == 400
    monkeypatch.setattr(studies, "withdrawal", lambda *a, **k: {"reason": "missing recording"})
    with pytest.raises(HTTPException) as error:
        download(edition, token, report, artifact)
    assert error.value.status_code == 409
