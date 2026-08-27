"""The injected faults, driven over a real socket by a real JWKS client.

**Why a real server here when every other test in this repository drives ASGI in-process.**
The faults exist for one caller: Chemclaw3's front door, which fetches this tenant's JWKS with
PyJWT's `PyJWKClient` over the network and maps *how* that fetch failed onto a status code — a
refused or erroring tenant is a 503 ("identity provider unavailable") and never a 401, because an
IdP outage is the deployment's failure and not the caller's bad credential. What a lane needs from
this repository is therefore not "the route returned 503" but "the client raised the class the
front door maps to 503", and that mapping happens inside `urllib`, which an ASGI transport never
reaches. So these run against `uvicorn` on an ephemeral port.

The three behaviours mirror, one for one, the ones Chemclaw3's `tests/test_entra_end_to_end.py`
proves in-process against a throwaway issuer: an unreachable tenant, a tenant answering 200 with
something that is not a key set, and a signing-key rotation.
"""

import json
import socket
import threading
import time

import httpx
import jwt
import pytest
import uvicorn
from jwt import PyJWKClient, PyJWKSet

from app.config import settings
from app.entra import keys

TENANT = "mock-tenant"
AUDIENCE = "api://chemclaw-test"


@pytest.fixture
def tenant(monkeypatch):
    """The mock served by uvicorn on an ephemeral port, with both switches on.

    Yields the base URL. `MOCK_ENTRA_FAULT_INJECTION` is a second switch beside
    `MOCK_ENTRA_ENABLED` on purpose — see `app/entra/faults.py` — so a test of the faults has to
    ask for both.
    """
    monkeypatch.setattr(settings, "entra_enabled", True)
    monkeypatch.setattr(settings, "entra_fault_injection", True)
    monkeypatch.setattr(settings, "eln_seed_on_startup", False)

    from app.main import app

    bound = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bound.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bound.bind(("127.0.0.1", 0))
    port = bound.getsockname()[1]
    monkeypatch.setattr(settings, "entra_issuer", f"http://127.0.0.1:{port}/entra/{TENANT}/v2.0")
    monkeypatch.setattr(settings, "entra_audience", AUDIENCE)

    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [bound]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "the mock backend did not start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _keys_url(base):
    """The endpoint Chemclaw3's `CHEMCLAW_ENTRA_JWKS_URL` is pointed at."""
    return f"{base}/entra/{TENANT}/discovery/v2.0/keys"


def _arm(base, fault):
    """Ask the tenant to serve `fault` from its keys endpoint, and return the new state."""
    response = httpx.post(f"{base}/entra/{TENANT}/_control/jwks-fault", json={"fault": fault})
    assert response.status_code == 200, response.text
    return response.json()


def _rotate(base):
    """Rotate the signing key, and return the new state."""
    response = httpx.post(f"{base}/entra/{TENANT}/_control/rotate-signing-key")
    assert response.status_code == 200, response.text
    return response.json()


def _mint(base, **request):
    """Mint a token for the identity asked for."""
    response = httpx.post(f"{base}/entra/{TENANT}/oauth2/v2.0/token", json=request)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_an_armed_outage_is_the_failure_class_a_front_door_answers_503_for(tenant):
    """The tenant refuses to serve its keys, and `PyJWKClient` says so as a connection error.

    `PyJWKClient.fetch_data` catches `URLError`, and `HTTPError` is one — so a 5xx from this route
    surfaces as `PyJWKClientConnectionError`, the class Chemclaw3's `api/auth.py` turns into
    `IdentityProviderUnavailable` and a 503. That chain is the whole reason the fault serves a
    status rather than an empty body.
    """
    client = PyJWKClient(_keys_url(tenant), cache_keys=False)
    assert client.get_signing_keys(), "the tenant did not serve its keys before the fault"

    _arm(tenant, "unavailable")
    with pytest.raises(jwt.PyJWKClientConnectionError):
        PyJWKClient(_keys_url(tenant), cache_keys=False).get_signing_keys()

    _arm(tenant, "none")
    assert PyJWKClient(_keys_url(tenant), cache_keys=False).get_signing_keys()


@pytest.mark.parametrize(
    ("fault", "expected"),
    [("malformed", json.JSONDecodeError), ("not_a_key_set", jwt.PyJWKSetError)],
)
def test_a_200_that_is_not_a_key_set_fails_in_the_library_the_front_door_expects(
    tenant, fault, expected
):
    """Two shapes, because they die in two different libraries and both must reach the 503 arm.

    An intercepting proxy's HTML page dies in `json.load` (`JSONDecodeError`, a `ValueError`, which
    PyJWT does not convert); a tenant answering JSON that is not a key set dies in
    `PyJWKSet.from_dict` (`PyJWKSetError`). Chemclaw3 catches `(ValueError, jwt.PyJWTError)` for
    exactly this pair, so a mock that could only serve one of them would leave half of that handler
    unexercised by the live lane.
    """
    _arm(tenant, fault)
    with pytest.raises(expected):
        PyJWKClient(_keys_url(tenant), cache_keys=False).get_signing_keys()


def test_a_rotated_key_is_published_beside_the_old_one_and_signs_the_next_token(tenant):
    """A rotation the front door can follow: the new `kid` resolves, and the old one still does.

    Chemclaw3 refreshes its cached key set when a token names a `kid` it does not hold, bounded by
    a cooldown. Publishing the new key *beside* the old one is what a tenant does — tokens minted
    a minute before a rotation must keep validating — so it is what this mints.
    """
    before = _mint(tenant, oid="u-alice")
    state = _rotate(tenant)
    after = _mint(tenant, oid="u-alice")

    assert state["signing_kid"] != keys.PUBLISHED_KID
    assert state["published_kids"] == [keys.PUBLISHED_KID, state["signing_kid"]]
    assert jwt.get_unverified_header(after)["kid"] == state["signing_kid"]
    assert jwt.get_unverified_header(before)["kid"] == keys.PUBLISHED_KID

    client = PyJWKClient(_keys_url(tenant), cache_keys=False)
    for token in (before, after):
        claims = jwt.decode(
            token,
            client.get_signing_key_from_jwt(token).key,
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=settings.entra_issuer,
        )
        assert claims["oid"] == "u-alice"


def test_the_key_set_is_still_a_key_set_when_nothing_is_armed(tenant):
    """The unarmed route is byte-identical to what it served before faults existed."""
    served = httpx.get(_keys_url(tenant))
    assert served.status_code == 200
    assert [key.key_id for key in PyJWKSet.from_dict(served.json()).keys] == [keys.PUBLISHED_KID]
