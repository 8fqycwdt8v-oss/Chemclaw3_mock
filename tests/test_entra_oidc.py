"""The browser sign-in: authorization code + PKCE, as `@azure/msal-browser` drives it.

Each test walks the protocol the way MSAL does — `/authorize` with a challenge and a nonce, the
login page, the redirect back with a code in the fragment, a cross-origin form POST redeeming it
with the verifier — and then checks the result the way the two readers check it: the access token
by the book Chemclaw3's front door uses (RS256 against the JWKS, audience, issuer, `exp` required),
and the id_token the way MSAL does (the `nonce` it sent).

Half of the file is refusals, for the same reason half of `test_entra.py` is: a tenant that lets a
wrong verifier, a wrong redirect URI or a replayed code through would make every green browser run
evidence about nothing.
"""

import base64
import hashlib
import json
import re
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
import pytest
from fastapi.testclient import TestClient
from jwt import PyJWK

from app.config import settings

TENANT = "mock-tenant"
ISSUER = f"http://testserver/entra/{TENANT}/v2.0"
AUDIENCE = "api://chemclaw-test"
CLIENT_ID = "spa-client"
SPA_ORIGIN = "http://127.0.0.1:4321"
REDIRECT_URI = f"{SPA_ORIGIN}/auth/callback"
SCOPE = f"{AUDIENCE}/Chat.Access openid profile offline_access"
BASE = f"/entra/{TENANT}/oauth2/v2.0"


@pytest.fixture
def tenant(monkeypatch):
    """The mock app with the tenant on and one SPA registration, as the UI's e2e lane wires it."""
    monkeypatch.setattr(settings, "entra_enabled", True)
    monkeypatch.setattr(settings, "entra_issuer", ISSUER)
    monkeypatch.setattr(settings, "entra_audience", AUDIENCE)
    monkeypatch.setattr(settings, "entra_spa_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "entra_redirect_uris", [REDIRECT_URI])
    monkeypatch.setattr(settings, "entra_users_json", "")
    monkeypatch.setattr(settings, "eln_seed_on_startup", False)

    from app.main import app

    with TestClient(app, follow_redirects=False) as client:
        yield client


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _authorize_params(challenge: str, **overrides: str) -> dict[str, str]:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "response_mode": "fragment",
        "scope": SCOPE,
        "state": "state-123",
        "nonce": "nonce-abc",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "client_info": "1",
    }
    params.update(overrides)
    return {key: value for key, value in params.items() if value is not None}


def _fragment(response) -> dict[str, str]:
    """The parameters a redirect delivered to the SPA, from its fragment (or query)."""
    assert response.status_code == 302, response.text
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == REDIRECT_URI
    raw = location.fragment or location.query
    return {key: values[0] for key, values in parse_qs(raw).items()}


def _sign_in(client, user: str = "alice", **overrides: str) -> tuple[dict[str, str], str]:
    """Run `/authorize` and the login page as `user`; return the redirect's params and verifier."""
    verifier, challenge = _pkce()
    page = client.get(f"{BASE}/authorize", params=_authorize_params(challenge, **overrides))
    assert page.status_code == 200, page.text
    request_id = re.search(r'name=request_id value="([^"]+)"', page.text).group(1)
    chosen = client.post(
        f"{BASE}/authorize",
        content=urlencode({"request_id": request_id, "user": user}),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    return _fragment(chosen), verifier


def _token(client, form: dict[str, str], origin: str | None = SPA_ORIGIN):
    headers = {"content-type": "application/x-www-form-urlencoded;charset=utf-8"}
    if origin is not None:
        headers["origin"] = origin
    return client.post(f"{BASE}/token", content=urlencode(form), headers=headers)


def _redeem(client, code: str, verifier: str, **overrides: str):
    form = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "scope": SCOPE,
        "client_info": "1",
    }
    form.update(overrides)
    return _token(client, form)


def _verify_access(client, token: str) -> dict:
    """Validate as Chemclaw3's front door does: RS256, the JWKS key, audience, issuer, exp."""
    keys = client.get(f"/entra/{TENANT}/discovery/v2.0/keys").json()["keys"]
    kid = jwt.get_unverified_header(token)["kid"]
    key = PyJWK.from_dict(next(k for k in keys if k["kid"] == kid)).key
    return jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=AUDIENCE,
        issuer=ISSUER,
        options={"require": ["exp"]},
    )


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


# --- the happy path ----------------------------------------------------------------------------


def test_discovery_names_every_endpoint_msal_needs(tenant):
    document = tenant.get(
        f"/entra/{TENANT}/v2.0/.well-known/openid-configuration", headers={"origin": SPA_ORIGIN}
    )
    body = document.json()
    base = ISSUER.removesuffix("/v2.0")
    assert body["authorization_endpoint"] == f"{base}/oauth2/v2.0/authorize"
    assert body["token_endpoint"] == f"{base}/oauth2/v2.0/token"
    assert body["end_session_endpoint"] == f"{base}/oauth2/v2.0/logout"
    assert body["code_challenge_methods_supported"] == ["S256"]
    # MSAL fetches this cross-origin; without the header the browser discards the answer.
    assert document.headers["access-control-allow-origin"] == SPA_ORIGIN


def test_discovery_is_not_readable_from_an_unregistered_origin(tenant):
    document = tenant.get(
        f"/entra/{TENANT}/v2.0/.well-known/openid-configuration",
        headers={"origin": "https://elsewhere.test"},
    )
    assert "access-control-allow-origin" not in document.headers


def test_the_login_page_is_labelled_and_offers_the_presets(tenant):
    _, challenge = _pkce()
    page = tenant.get(f"{BASE}/authorize", params=_authorize_params(challenge))
    assert page.status_code == 200
    assert "TEST ONLY" in page.text
    for user in ("alice", "bob", "carol"):
        assert f'data-testid="mock-login-{user}"' in page.text


def test_a_signed_in_user_gets_tokens_both_readers_accept(tenant):
    """The whole flow, and the claims Chemclaw3 and the UI each read from what it issues."""
    delivered, verifier = _sign_in(tenant, "alice")
    assert delivered["state"] == "state-123"
    client_info = json.loads(base64.urlsafe_b64decode(delivered["client_info"] + "=="))
    assert client_info == {"uid": "00000000-0000-0000-0000-00000000a11c", "utid": TENANT}

    response = _redeem(tenant, delivered["code"], verifier)
    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == SPA_ORIGIN
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert f"{AUDIENCE}/Chat.Access" in body["scope"].split()

    access = _verify_access(tenant, body["access_token"])
    assert access["oid"] == "00000000-0000-0000-0000-00000000a11c"
    assert access["preferred_username"] == "alice@mock-tenant.test"
    assert access["roles"] == ["chemist", "reviewer"]
    assert access["scp"] == "Chat.Access"
    assert access["tid"] == TENANT
    assert access["azp"] == CLIENT_ID

    identity = _claims(body["id_token"])
    assert identity["aud"] == CLIENT_ID
    assert identity["iss"] == ISSUER
    assert identity["nonce"] == "nonce-abc"
    assert identity["oid"] == access["oid"]
    assert identity["name"] == "Alice Chemist"
    # The UI reads roles off the *id* token (`msalAuth.ts::toAccount`), not the access token.
    assert identity["roles"] == ["chemist", "reviewer"]
    assert body["refresh_token"]


def test_two_testers_are_two_identities(tenant):
    """The reason the flow exists: alice and bob, signed in separately, are different people."""
    alice, alice_verifier = _sign_in(tenant, "alice")
    alice_token = _redeem(tenant, alice["code"], alice_verifier).json()["access_token"]
    tenant.cookies.clear()
    bob, bob_verifier = _sign_in(tenant, "bob")
    bob_token = _redeem(tenant, bob["code"], bob_verifier).json()["access_token"]

    assert _verify_access(tenant, alice_token)["preferred_username"] == "alice@mock-tenant.test"
    assert _verify_access(tenant, bob_token)["preferred_username"] == "bob@mock-tenant.test"
    assert _verify_access(tenant, bob_token)["roles"] == ["chemist"]


def test_a_custom_identity_and_a_configured_user_list(tenant, monkeypatch):
    monkeypatch.setattr(
        settings,
        "entra_users_json",
        json.dumps({"dave": {"oid": "u-dave", "upn": "dave@x.test", "roles": ["admin"]}}),
    )
    _, challenge = _pkce()
    page = tenant.get(f"{BASE}/authorize", params=_authorize_params(challenge))
    assert 'data-testid="mock-login-dave"' in page.text
    assert "mock-login-alice" not in page.text

    verifier, challenge = _pkce()
    page = tenant.get(f"{BASE}/authorize", params=_authorize_params(challenge))
    request_id = re.search(r'name=request_id value="([^"]+)"', page.text).group(1)
    chosen = tenant.post(
        f"{BASE}/authorize",
        content=urlencode(
            {"request_id": request_id, "user": "custom", "oid": "u-erin", "roles": "a, b"}
        ),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    access = _verify_access(
        tenant, _redeem(tenant, _fragment(chosen)["code"], verifier).json()["access_token"]
    )
    assert access["oid"] == "u-erin"
    assert access["roles"] == ["a", "b"]


def test_query_response_mode_delivers_in_the_query(tenant):
    verifier, challenge = _pkce()
    page = tenant.get(
        f"{BASE}/authorize", params=_authorize_params(challenge, response_mode="query")
    )
    request_id = re.search(r'name=request_id value="([^"]+)"', page.text).group(1)
    chosen = tenant.post(
        f"{BASE}/authorize",
        content=urlencode({"request_id": request_id, "user": "bob"}),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    location = urlsplit(chosen.headers["location"])
    assert not location.fragment
    assert "code" in parse_qs(location.query)


def test_a_refresh_token_buys_a_new_access_token_for_the_same_person(tenant):
    delivered, verifier = _sign_in(tenant, "bob")
    refresh_token = _redeem(tenant, delivered["code"], verifier).json()["refresh_token"]

    refreshed = _token(
        tenant,
        {
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": SCOPE,
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    assert _verify_access(tenant, body["access_token"])["preferred_username"] == (
        "bob@mock-tenant.test"
    )
    # A refreshed id_token answers no authorization request, so it carries no nonce.
    assert "nonce" not in _claims(body["id_token"])
    assert body["refresh_token"]


def test_an_unknown_refresh_token_is_refused(tenant):
    refused = _token(
        tenant,
        {"client_id": CLIENT_ID, "grant_type": "refresh_token", "refresh_token": "nope"},
    )
    assert refused.status_code == 400
    assert refused.json()["error"] == "invalid_grant"


def test_a_signed_in_browser_is_signed_in_silently_next_time(tenant):
    """SSO: with the tenant's session cookie, `/authorize` answers with a code and no page —
    including `prompt=none`, MSAL's hidden-iframe silent sign-in."""
    _sign_in(tenant, "alice")
    for prompt in (None, "none"):
        verifier, challenge = _pkce()
        silent = tenant.get(f"{BASE}/authorize", params=_authorize_params(challenge, prompt=prompt))
        delivered = _fragment(silent)
        access = _redeem(tenant, delivered["code"], verifier).json()["access_token"]
        assert _verify_access(tenant, access)["preferred_username"] == "alice@mock-tenant.test"

    _, challenge = _pkce()
    forced = tenant.get(f"{BASE}/authorize", params=_authorize_params(challenge, prompt="login"))
    assert forced.status_code == 200, "prompt=login must show the page even with a session"


def test_prompt_none_without_a_session_is_login_required(tenant):
    _, challenge = _pkce()
    response = tenant.get(f"{BASE}/authorize", params=_authorize_params(challenge, prompt="none"))
    delivered = _fragment(response)
    assert delivered["error"] == "login_required"
    assert delivered["state"] == "state-123"


def test_logout_ends_the_session_and_returns_to_a_registered_origin(tenant):
    _sign_in(tenant, "alice")
    out = tenant.get(f"{BASE}/logout", params={"post_logout_redirect_uri": SPA_ORIGIN})
    assert out.status_code == 302
    assert out.headers["location"] == SPA_ORIGIN

    _, challenge = _pkce()
    after = tenant.get(f"{BASE}/authorize", params=_authorize_params(challenge, prompt="none"))
    assert _fragment(after)["error"] == "login_required"


def test_logout_does_not_redirect_to_an_unregistered_uri(tenant):
    out = tenant.get(f"{BASE}/logout", params={"post_logout_redirect_uri": "https://evil.test/"})
    assert out.status_code == 200
    assert "location" not in out.headers


# --- PKCE --------------------------------------------------------------------------------------


def test_a_wrong_verifier_is_refused_and_burns_the_code(tenant):
    delivered, verifier = _sign_in(tenant)
    wrong = _redeem(tenant, delivered["code"], secrets.token_urlsafe(48))
    assert wrong.status_code == 400
    assert wrong.json()["error"] == "invalid_grant"
    assert "code_challenge" in wrong.json()["error_description"]

    # The right verifier afterwards is too late: a failed redemption spends the code, so a
    # verifier cannot be guessed at.
    retry = _redeem(tenant, delivered["code"], verifier)
    assert retry.status_code == 400
    assert "already redeemed" in retry.json()["error_description"]


@pytest.mark.parametrize("verifier", ["", "too-short"])
def test_a_missing_or_malformed_verifier_is_refused(tenant, verifier):
    delivered, _ = _sign_in(tenant)
    refused = _redeem(tenant, delivered["code"], verifier)
    assert refused.status_code == 400
    assert refused.json()["error"] == "invalid_grant"


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"code_challenge": None, "code_challenge_method": None}, "AADSTS9002325"),
        ({"code_challenge_method": "plain"}, "S256"),
    ],
)
def test_authorize_without_s256_pkce_reports_an_error_to_the_client(tenant, overrides, fragment):
    _, challenge = _pkce()
    response = tenant.get(f"{BASE}/authorize", params=_authorize_params(challenge, **overrides))
    delivered = _fragment(response)
    assert delivered["error"] == "invalid_request"
    assert fragment in delivered["error_description"]
    assert "code" not in delivered


def test_a_code_is_single_use(tenant):
    delivered, verifier = _sign_in(tenant)
    assert _redeem(tenant, delivered["code"], verifier).status_code == 200
    replay = _redeem(tenant, delivered["code"], verifier)
    assert replay.status_code == 400
    assert "AADSTS54005" in replay.json()["error_description"]


# --- redirect URIs and clients -----------------------------------------------------------------


def test_an_unregistered_redirect_uri_is_an_error_page_never_a_redirect(tenant):
    """The open-redirect guard: an unregistered URI is never sent anything, error included."""
    _, challenge = _pkce()
    response = tenant.get(
        f"{BASE}/authorize",
        params=_authorize_params(challenge, redirect_uri="https://evil.test/auth/callback"),
    )
    assert response.status_code == 400
    assert "location" not in response.headers
    assert "AADSTS50011" in response.text


def test_an_unknown_client_is_an_error_page(tenant):
    _, challenge = _pkce()
    response = tenant.get(
        f"{BASE}/authorize", params=_authorize_params(challenge, client_id="someone-else")
    )
    assert response.status_code == 400
    assert "location" not in response.headers
    assert "AADSTS700016" in response.text


def test_a_code_redeemed_against_another_redirect_uri_is_refused(tenant):
    delivered, verifier = _sign_in(tenant)
    refused = _redeem(
        tenant, delivered["code"], verifier, redirect_uri=f"{SPA_ORIGIN}/somewhere-else"
    )
    assert refused.status_code == 400
    assert refused.json()["error"] == "invalid_grant"
    assert "redirect_uri" in refused.json()["error_description"]


def test_a_code_redeemed_by_another_client_is_refused(tenant):
    delivered, verifier = _sign_in(tenant)
    refused = _redeem(tenant, delivered["code"], verifier, client_id="someone-else")
    assert refused.status_code == 400
    assert refused.json()["error"] == "invalid_grant"


# --- nonce -------------------------------------------------------------------------------------


@pytest.mark.parametrize("nonce", ["n-1", "a different nonce entirely"])
def test_the_id_token_echoes_exactly_the_nonce_it_was_asked_for(tenant, nonce):
    delivered, verifier = _sign_in(tenant, nonce=nonce)
    identity = _claims(_redeem(tenant, delivered["code"], verifier).json()["id_token"])
    assert identity["nonce"] == nonce


def test_no_nonce_asked_for_means_none_in_the_id_token(tenant):
    """MSAL rejects an id_token carrying a nonce it did not send (`nonce_mismatch`), so a tenant
    inventing one would fail sign-ins that should succeed."""
    delivered, verifier = _sign_in(tenant, nonce=None)
    identity = _claims(_redeem(tenant, delivered["code"], verifier).json()["id_token"])
    assert "nonce" not in identity


# --- scopes ------------------------------------------------------------------------------------


def test_a_scope_for_another_api_is_refused(tenant):
    """What a UI whose `API_SCOPE` names the wrong API meets — from Entra, and from this."""
    _, challenge = _pkce()
    response = tenant.get(
        f"{BASE}/authorize",
        params=_authorize_params(challenge, scope="api://someone-else/Chat.Access openid"),
    )
    delivered = _fragment(response)
    assert delivered["error"] == "invalid_resource"
    assert "AADSTS500011" in delivered["error_description"]


def test_two_resources_in_one_request_are_refused(tenant):
    _, challenge = _pkce()
    response = tenant.get(
        f"{BASE}/authorize",
        params=_authorize_params(
            challenge, scope=f"{AUDIENCE}/Chat.Access api://other/x openid"
        ),
    )
    assert _fragment(response)["error"] == "invalid_scope"


# --- the token endpoint's cross-origin rule and CORS -------------------------------------------


def test_a_code_redeemed_without_an_origin_is_refused(tenant):
    """The SPA platform's rule: a SPA's code is redeemable cross-origin only, so a `curl` replay
    of a code lifted from a URL bar does not work."""
    delivered, verifier = _sign_in(tenant)
    form = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": delivered["code"],
        "code_verifier": verifier,
    }
    refused = _token(tenant, form, origin=None)
    assert refused.status_code == 400
    assert "AADSTS9002327" in refused.json()["error_description"]


def test_a_code_redeemed_from_an_unregistered_origin_is_refused(tenant):
    delivered, verifier = _sign_in(tenant)
    form = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": delivered["code"],
        "code_verifier": verifier,
    }
    refused = _token(tenant, form, origin="https://evil.test")
    assert refused.status_code == 400
    assert "access-control-allow-origin" not in refused.headers


def test_the_token_preflight_answers_a_registered_origin_only(tenant):
    asked = {
        "origin": SPA_ORIGIN,
        "access-control-request-method": "POST",
        "access-control-request-headers": "content-type,x-client-current-telemetry",
    }
    allowed = tenant.options(f"{BASE}/token", headers=asked)
    assert allowed.status_code == 204
    assert allowed.headers["access-control-allow-origin"] == SPA_ORIGIN
    assert "x-client-current-telemetry" in allowed.headers["access-control-allow-headers"]

    refused = tenant.options(f"{BASE}/token", headers={**asked, "origin": "https://evil.test"})
    assert refused.status_code == 403
    assert "access-control-allow-origin" not in refused.headers


def test_an_unsupported_grant_is_named(tenant):
    refused = _token(tenant, {"grant_type": "client_credentials", "client_id": CLIENT_ID})
    assert refused.status_code == 400
    assert refused.json()["error"] == "unsupported_grant_type"


# --- the switch, and the mint beside it --------------------------------------------------------


def test_everything_is_off_unless_the_tenant_is_enabled(tenant, monkeypatch):
    monkeypatch.setattr(settings, "entra_enabled", False)
    _, challenge = _pkce()
    assert tenant.get(f"{BASE}/authorize", params=_authorize_params(challenge)).status_code == 404
    assert _token(tenant, {"grant_type": "authorization_code"}).status_code == 404


def test_the_json_mint_still_answers_on_the_same_url(tenant):
    """The token route serves both callers; adding the form flow must not move the JSON one."""
    minted = tenant.post(f"{BASE}/token", json={"oid": "u-alice"})
    assert minted.status_code == 200
    assert _verify_access(tenant, minted.json()["access_token"])["oid"] == "u-alice"

    assert tenant.post(f"{BASE}/token", json={}).status_code == 422
    assert tenant.post(
        f"{BASE}/token", content=b"not json", headers={"content-type": "application/json"}
    ).status_code == 422
