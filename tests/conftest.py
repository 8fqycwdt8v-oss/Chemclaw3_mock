import pytest
from fastapi.testclient import TestClient

from app.config import settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "eln_export_dir", tmp_path / "eln")
    monkeypatch.setattr(settings, "ord_export_dir", tmp_path / "ord")
    monkeypatch.setattr(settings, "hte_max_records_per_dataset", 5)

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
