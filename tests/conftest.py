import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.entra import faults, keys, oidc


@pytest.fixture(autouse=True)
def _tenant_state_per_test():
    """Put the stand-in tenant's key set, armed fault and sign-in state back between tests.

    All of it lives at module scope in `app/entra/` — a signing key set is process state, so is a
    fault somebody armed over HTTP, and so are the browser sign-in's codes, refresh tokens and
    sessions — so without this a test that rotates or breaks the tenant
    changes what every later test is running against. Around each test rather than after, so an
    ordering the suite grows into cannot make one of them depend on the previous one's cleanup.
    """
    keys.reset()
    faults.reset()
    oidc.reset()
    yield
    keys.reset()
    faults.reset()
    oidc.reset()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "eln_export_dir", tmp_path / "eln")
    monkeypatch.setattr(settings, "ord_export_dir", tmp_path / "ord")
    monkeypatch.setattr(settings, "hte_max_records_per_dataset", 5)

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
