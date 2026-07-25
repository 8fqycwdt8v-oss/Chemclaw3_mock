import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.hpc.store import job_store

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "eln_export_dir", tmp_path / "eln")
    monkeypatch.setattr(settings, "ord_export_dir", tmp_path / "ord")
    monkeypatch.setattr(settings, "hpc_api_token", "test-token")
    monkeypatch.setattr(settings, "hpc_artifact_store_token", "")
    monkeypatch.setattr(settings, "hpc_enforce_auth", True)
    monkeypatch.setattr(settings, "hpc_polls_until_done", 2)
    monkeypatch.setattr(settings, "hpc_unknown_status_every_n_polls", 0)
    job_store.reset()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    job_store.reset()
