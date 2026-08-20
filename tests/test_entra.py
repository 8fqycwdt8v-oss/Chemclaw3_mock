"""The stand-in tenant: what it publishes, what it mints, and that a resource server agrees.

The last of those is the point of the file. A mock IdP that only satisfies its own assertions is a
mock of nothing — the question is whether Chemclaw3's front door, which checks an RS256 signature
against this JWKS plus the audience and the issuer, accepts what this mints and refuses what it
deliberately breaks. `test_a_resource_server_validating_by_the_book_agrees` is that check, written
against PyJWT with the same options Chemclaw3 passes rather than against Chemclaw3 (which is not
installed here): the contract is the JWT spec, and this asserts against the spec.
"""

import jwt
import pytest
from fastapi.testclient import TestClient
from jwt import PyJWK

from app.config import settings
from app.entra.keys import PUBLISHED_KID, UNPUBLISHED_KID

TENANT = "mock-tenant"
ISSUER = f"http://testserver/entra/{TENANT}/v2.0"
AUDIENCE = "api://chemclaw-test"


@pytest.fixture
def tenant(monkeypatch):
    """The mock app with its tenant switched on, and issuer/audience pinned for the test."""
    monkeypatch.setattr(settings, "entra_enabled", True)
    monkeypatch.setattr(settings, "entra_issuer", ISSUER)
    monkeypatch.setattr(settings, "entra_audience", AUDIENCE)
    monkeypatch.setattr(settings, "eln_seed_on_startup", False)

    from app.main import app

    with TestClient(app) as client:
        yield client


def _mint(client, **request):
    """Ask the tenant for a token, and fail loudly rather than returning an error body."""
    response = client.post(f"/entra/{TENANT}/oauth2/v2.0/token", json=request)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _verify(client, token, **overrides):
    """Validate `token` the way Chemclaw3's front door does, and return its claims.

    The same four checks in the same shape: RS256 only, the signature against the key the JWKS
    publishes for the token's `kid`, the audience, the issuer, and `exp` *required* rather than
    merely checked when present.
    """
    keys = client.get(f"/entra/{TENANT}/discovery/v2.0/keys").json()["keys"]
    kid = jwt.get_unverified_header(token)["kid"]
    matching = [key for key in keys if key["kid"] == kid]
    if not matching:
        raise jwt.PyJWKClientError(f"no published key for kid {kid!r}")
    options = {"require": ["exp"]}
    return jwt.decode(
        token,
        PyJWK.from_dict(matching[0]).key,
        algorithms=["RS256"],
        audience=overrides.get("audience", AUDIENCE),
        issuer=overrides.get("issuer", ISSUER),
        options=options,
    )


def test_the_jwks_publishes_exactly_one_key(tenant):
    """One key, and the forgery key is not it — the absence is what makes forgery testable."""
    keys = tenant.get(f"/entra/{TENANT}/discovery/v2.0/keys").json()["keys"]
    assert [key["kid"] for key in keys] == [PUBLISHED_KID]
    assert keys[0]["kty"] == "RSA"
    assert keys[0]["alg"] == "RS256"


def test_discovery_points_at_the_routes_that_exist(tenant):
    """The document a human curls when they want to know whether this is wired up."""
    document = tenant.get(f"/entra/{TENANT}/v2.0/.well-known/openid-configuration").json()
    assert document["issuer"] == ISSUER
    assert tenant.get(document["jwks_uri"]).status_code == 200


def test_a_resource_server_validating_by_the_book_agrees(tenant):
    """A minted token survives the four checks Chemclaw3's front door performs, and carries its
    identity through.

    This is the assertion the rest of the file exists to support: without it the tenant is a mock
    of nothing, satisfying only its own idea of a token.
    """
    token = _mint(
        tenant,
        oid="u-alice",
        upn="alice@corp.example",
        roles=["process-chemist"],
        groups=["11111111-2222-3333-4444-555555555555"],
    )
    claims = _verify(tenant, token)
    assert claims["oid"] == "u-alice"
    assert claims["preferred_username"] == "alice@corp.example"
    assert claims["roles"] == ["process-chemist"]
    assert claims["groups"] == ["11111111-2222-3333-4444-555555555555"]
    assert claims["tid"] == TENANT


@pytest.mark.parametrize(
    ("name", "request_body", "expected"),
    [
        ("another resource", {"audience": "api://someone-else"}, jwt.InvalidAudienceError),
        ("another issuer", {"issuer": "https://attacker.test/v2.0"}, jwt.InvalidIssuerError),
        ("already expired", {"expires_in": -60}, jwt.ExpiredSignatureError),
        ("no expiry at all", {"omit_expiry": True}, jwt.MissingRequiredClaimError),
        ("a key we never published", {"unpublished_key": True}, jwt.PyJWKClientError),
    ],
)
def test_each_deliberate_flaw_is_one_a_resource_server_catches(
    tenant, name, request_body, expected
):
    """Every override mints a token that is refused, and refused for the stated reason.

    Asserting the *class* rather than "it raised" is what keeps these honest: an expired token that
    happened to be refused for a bad audience would prove nothing about the expiry check, and a
    lane built on top of these would be testing the wrong refusal.
    """
    token = _mint(tenant, oid="u-attacker", **request_body)
    with pytest.raises(expected):
        _verify(tenant, token)


def test_a_forged_token_names_a_real_key_and_still_fails_on_the_signature(tenant):
    """The forgery is only detectable at the signature, which is the case worth having.

    Its `kid` names the unpublished key, so resolution fails first — but point the verifier at the
    published key, as a resource server would if the forger had copied a real `kid`, and the
    signature check is what refuses it.
    """
    token = _mint(tenant, oid="u-attacker", unpublished_key=True)
    assert jwt.get_unverified_header(token)["kid"] == UNPUBLISHED_KID

    published = tenant.get(f"/entra/{TENANT}/discovery/v2.0/keys").json()["keys"][0]
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(
            token,
            PyJWK.from_dict(published).key,
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
        )


def test_the_tenant_is_off_unless_a_run_asks_for_it(monkeypatch):
    """Disabled, minting is a 404 — the default, because this endpoint forges credentials.

    The keys route stays answerable either way: a JWKS is a public document, and 404ing it would
    make a misconfigured lane look like a network fault rather than a switch nobody flipped.
    """
    monkeypatch.setattr(settings, "entra_enabled", False)
    monkeypatch.setattr(settings, "eln_seed_on_startup", False)

    from app.main import app

    with TestClient(app) as client:
        minted = client.post(f"/entra/{TENANT}/oauth2/v2.0/token", json={"oid": "u-1"})
        assert minted.status_code == 404
        assert client.get(f"/entra/{TENANT}/discovery/v2.0/keys").status_code == 200
