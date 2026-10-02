"""The browser sign-in: authorization code + PKCE, so MSAL.js can sign a tester in. **TEST ONLY.**

**Why this exists when `router.py`'s mint already hands out any token.** The mint is for a driver
that holds the token itself — a shell script, a probe, a Playwright fixture injecting a header.
What it cannot stand in for is the *browser* half of authentication: Chemclaw3_ui running
`AUTH_MODE=msal` sends its chemist to an authority, gets a code back on `/auth/callback`, redeems
it with a PKCE verifier from the page, refreshes silently, and signs out through the authority's
end-session endpoint. None of that ran anywhere but against a real Entra tenant, so a browser test
of the system with two distinct people in it was not possible at all. This module is that
authority, for exactly the subset of the protocol `@azure/msal-browser` uses.

**What it is faithful about, and why each one.** A mock is worth what it is faithful about, and
each check here is one a real tenant makes and a misconfigured UI would otherwise sail through:

- the client id must be the one SPA registration this tenant knows (AADSTS700016);
- the redirect URI must be registered, exactly (AADSTS50011) — and a bad one is answered with an
  error *page*, never a redirect, because redirecting to an unvalidated URI is the open redirect;
- PKCE is required and must be S256, and the verifier must hash to the challenge at redemption;
- a code is single-use, short-lived, and bound to the client and redirect URI it was issued for;
- the token endpoint answers only cross-origin requests from a registered origin (the SPA
  platform's rule: AADSTS9002327), with the CORS headers `fetch` needs;
- one resource per request, and that resource must be the API this tenant was told about
  (`MOCK_ENTRA_AUDIENCE`), or the scope is refused (AADSTS500011) — the same refusal a UI whose
  `API_SCOPE` names the wrong API gets from Entra;
- the id_token echoes the request's `nonce`, carries `aud` = the SPA client id and `roles`; the
  access token carries `aud` = the API, `scp`, `roles`, `oid`, `tid` and `preferred_username` —
  the claims Chemclaw3's `api/auth.py` reads;
- `client_info` is returned the way Entra returns it, so MSAL builds the same `homeAccountId`
  shape (`oid.tid`) it builds in production, in its default (`AAD`) protocol mode.

**What it is deliberately not.** There are no passwords: the login page *is* the choice of
identity, which is the point of a test tenant. There is no consent, no client secret, no
conditional access and no MFA. Users are a preset list (`MOCK_ENTRA_USERS`) plus a free-form row,
and every one of them is whoever the tester says they are. That is why it sits behind
`MOCK_ENTRA_ENABLED` with the mint, and why it must never be reachable from anywhere that matters.

**Everything is process memory.** Codes, refresh tokens and sign-in sessions live in module dicts
and die with the process, as the signing keys do. `reset()` exists for the suite's fixtures.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.config import settings
from app.entra import keys

router = APIRouter(prefix="/entra", tags=["entra"])

#: The testers the login page offers when `MOCK_ENTRA_USERS` is unset. Three, because the cases a
#: browser test of a shared system needs are "two different people" and "someone with no roles".
PRESET_USERS: dict[str, dict[str, object]] = {
    "alice": {
        "oid": "00000000-0000-0000-0000-00000000a11c",
        "upn": "alice@mock-tenant.test",
        "name": "Alice Chemist",
        "roles": ["chemist", "reviewer"],
    },
    "bob": {
        "oid": "00000000-0000-0000-0000-000000000b0b",
        "upn": "bob@mock-tenant.test",
        "name": "Bob Chemist",
        "roles": ["chemist"],
    },
    "carol": {
        "oid": "00000000-0000-0000-0000-0000000ca201",
        "upn": "carol@mock-tenant.test",
        "name": "Carol Visitor",
        "roles": [],
    },
}

#: The scopes that are about the *sign-in* rather than about a resource. Entra issues them to every
#: client without a resource, and MSAL adds all three to every request on its own.
OIDC_SCOPES = frozenset({"openid", "profile", "offline_access", "email"})

#: Lifetimes. A code lives ten minutes (Entra's documented bound), a token an hour, and a SPA
#: refresh token 24 hours — the SPA platform's fixed lifetime.
CODE_TTL = 600
TOKEN_TTL = 3600
REFRESH_TTL = 24 * 3600
PENDING_TTL = 900

#: RFC 7636 §4.1: 43-128 characters from the unreserved set.
_VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")


@dataclass
class Identity:
    """Who signed in. `key` is the preset name, or `custom` for the free-form row."""

    key: str
    oid: str
    upn: str
    name: str
    roles: list[str] = field(default_factory=list)


@dataclass
class AuthorizeRequest:
    """A validated `/authorize` request, waiting for the tester to choose who they are."""

    tenant: str
    client_id: str
    redirect_uri: str
    response_mode: str
    state: str | None
    nonce: str | None
    scopes: list[str]
    resource: str | None
    code_challenge: str
    client_info: bool
    created: float


@dataclass
class Grant:
    """What a code or a refresh token stands for: one identity, one client, one set of scopes."""

    tenant: str
    client_id: str
    identity: Identity
    scopes: list[str]
    resource: str | None
    expires: float
    # Code-only: the redirect URI and PKCE challenge it was issued against, and the nonce the
    # id_token must echo.
    redirect_uri: str = ""
    code_challenge: str = ""
    nonce: str | None = None
    used: bool = False


_pending: dict[str, AuthorizeRequest] = {}
_codes: dict[str, Grant] = {}
_refresh_tokens: dict[str, Grant] = {}
_sessions: dict[str, Identity] = {}


def reset() -> None:
    """Forget every pending sign-in, code, refresh token and session. For the suite's fixtures."""
    _pending.clear()
    _codes.clear()
    _refresh_tokens.clear()
    _sessions.clear()


class OAuthError(Exception):
    """An OAuth error the protocol says to *report* — by redirect at `/authorize`, JSON at
    `/token`. Distinct from a client or redirect URI that cannot be trusted with a redirect."""

    def __init__(self, error: str, description: str, status: int = 400) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status = status


# --- configuration, read per call so tests (and a reader of this file) see one source ----------


def users() -> dict[str, Identity]:
    """The testers the login page offers: `MOCK_ENTRA_USERS`, or the presets.

    Read per call rather than once, like everything else in this module that reads `settings`, so
    a test that pins a value sees it and a reader does not have to wonder when it was read.
    """
    raw: dict[str, dict[str, object]] = (
        json.loads(settings.entra_users_json) if settings.entra_users_json.strip() else PRESET_USERS
    )
    return {
        key: Identity(
            key=key,
            oid=str(entry["oid"]),
            upn=str(entry.get("upn", "")),
            name=str(entry.get("name", key)),
            roles=[str(role) for role in entry.get("roles", [])],  # type: ignore[union-attr]
        )
        for key, entry in raw.items()
    }


def _origin(uri: str) -> str:
    parts = urlsplit(uri)
    return f"{parts.scheme}://{parts.netloc}"


def allowed_origins() -> set[str]:
    """The origins of the registered redirect URIs — the only callers the token endpoint serves."""
    return {_origin(uri) for uri in settings.entra_redirect_uris}


def cors_headers(request: Request) -> dict[str, str]:
    """CORS headers for a registered origin, nothing for any other.

    MSAL fetches discovery and redeems codes with `fetch` from the SPA's origin, so both need
    `Access-Control-Allow-Origin` or the browser discards the answer. Reflecting the one origin
    rather than `*` keeps an unregistered page from reading this tenant's answers at all.
    """
    origin = request.headers.get("origin", "")
    if origin and origin in allowed_origins():
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
    return {}


def preflight(request: Request) -> Response:
    """Answer a CORS preflight for the token endpoint.

    MSAL's token POST is not a "simple" request — it carries `x-client-*` telemetry headers — so
    the browser asks first. The requested headers are reflected because MSAL's set changes between
    versions and none of them carries anything this tenant acts on.
    """
    headers = cors_headers(request)
    if not headers:
        return Response(status_code=403)
    headers.update(
        {
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": request.headers.get(
                "access-control-request-headers", "content-type"
            ),
            "Access-Control-Max-Age": "600",
        }
    )
    return Response(status_code=204, headers=headers)


def _require_enabled() -> None:
    if not settings.entra_enabled:
        raise _Disabled()


class _Disabled(Exception):
    pass


def _disabled() -> JSONResponse:
    # The same 404 and wording as the mint: no credential would make this work.
    return JSONResponse(status_code=404, content={"detail": "mock entra tenant is disabled"})


# --- scopes ------------------------------------------------------------------------------------


def parse_scopes(raw: str) -> tuple[list[str], str | None]:
    """Split a scope string into its scopes and the one resource they name, if any.

    `api://chemclaw/Chat.Access` names the resource `api://chemclaw`. Entra refuses a request
    naming two resources, and refuses a resource it has no service principal for — here, anything
    but `MOCK_ENTRA_AUDIENCE`. That second refusal is what a UI with the wrong `API_SCOPE` meets.
    """
    scopes = [scope for scope in raw.split() if scope]
    resources = set()
    for scope in scopes:
        if scope in OIDC_SCOPES:
            continue
        if "/" not in scope.removeprefix("api://"):
            raise OAuthError(
                "invalid_scope",
                f"AADSTS70011: The provided value for scope {scope!r} is not valid: a resource "
                "scope names its API and the permission, e.g. api://chemclaw/Chat.Access.",
            )
        resources.add(scope.rsplit("/", 1)[0])
    if len(resources) > 1:
        raise OAuthError(
            "invalid_scope",
            "AADSTS28000: Provided value for the input parameter scope is not valid because it "
            f"contains more than one resource: {sorted(resources)}.",
        )
    resource = resources.pop() if resources else None
    if resource is not None and resource != settings.entra_audience:
        raise OAuthError(
            "invalid_resource",
            f"AADSTS500011: The resource principal named {resource} was not found in the tenant. "
            f"This mock tenant knows one API: {settings.entra_audience}.",
        )
    return scopes, resource


# --- tokens ------------------------------------------------------------------------------------


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _sub(oid: str, client_id: str) -> str:
    """A pairwise `sub`, as Entra issues it: stable per user *and* app, unlike `oid`."""
    return _b64url(hashlib.sha256(f"{oid}:{client_id}".encode()).digest())


def client_info(identity: Identity, tenant: str) -> str:
    """Entra's `client_info`: `{"uid": oid, "utid": tid}`, base64url. MSAL builds the account's
    `homeAccountId` (`uid.utid`) from it in its default protocol mode."""
    return _b64url(json.dumps({"uid": identity.oid, "utid": tenant}).encode())


def _sign(claims: dict[str, object]) -> str:
    kid = keys.signing_kid()
    return jwt.encode(claims, keys.private_pem(kid), algorithm="RS256", headers={"kid": kid})


def issue_tokens(grant: Grant, *, nonce: str | None) -> dict[str, object]:
    """The token endpoint's success body for `grant`: access, id and refresh tokens."""
    now = int(time.time())
    identity = grant.identity
    common: dict[str, object] = {
        "iss": settings.entra_issuer,
        "iat": now,
        "nbf": now,
        "exp": now + TOKEN_TTL,
        "oid": identity.oid,
        "tid": grant.tenant,
        "preferred_username": identity.upn,
        "name": identity.name,
        "ver": "2.0",
    }
    if identity.roles:
        common["roles"] = list(identity.roles)

    resource_scopes = [scope for scope in grant.scopes if scope not in OIDC_SCOPES]
    if grant.resource is not None:
        access_claims = {
            **common,
            "aud": grant.resource,
            "sub": _sub(identity.oid, grant.resource),
            "azp": grant.client_id,
            "azpacr": "0",
            "scp": " ".join(scope.rsplit("/", 1)[1] for scope in resource_scopes),
            "uti": secrets.token_urlsafe(16),
        }
        granted = resource_scopes
    else:
        # No resource asked for: Entra issues a Graph token for the OIDC scopes. Nothing here reads
        # it; it exists so the response has the shape MSAL expects.
        access_claims = {
            **common,
            "aud": "00000003-0000-0000-c000-000000000000",
            "sub": _sub(identity.oid, "graph"),
            "azp": grant.client_id,
            "scp": " ".join(scope for scope in grant.scopes if scope != "offline_access"),
        }
        granted = [scope for scope in grant.scopes if scope != "offline_access"]

    body: dict[str, object] = {
        "token_type": "Bearer",
        "scope": " ".join(granted),
        "expires_in": TOKEN_TTL,
        "ext_expires_in": TOKEN_TTL,
        "access_token": _sign(access_claims),
        "client_info": client_info(identity, grant.tenant),
    }
    if "openid" in grant.scopes:
        id_claims = {**common, "aud": grant.client_id, "sub": _sub(identity.oid, grant.client_id)}
        if nonce is not None:
            id_claims["nonce"] = nonce
        body["id_token"] = _sign(id_claims)
    if "offline_access" in grant.scopes:
        refresh_token = secrets.token_urlsafe(48)
        _refresh_tokens[refresh_token] = Grant(
            tenant=grant.tenant,
            client_id=grant.client_id,
            identity=identity,
            scopes=list(grant.scopes),
            resource=grant.resource,
            expires=time.time() + REFRESH_TTL,
        )
        body["refresh_token"] = refresh_token
    return body


# --- /authorize --------------------------------------------------------------------------------


def _error_page(status: int, title: str, detail: str) -> HTMLResponse:
    """An error the tenant cannot redirect: the client or redirect URI is not one it trusts."""
    return HTMLResponse(
        status_code=status,
        content=_page(
            f"<h1>{html.escape(title)}</h1><p class=err>{html.escape(detail)}</p>"
            "<p>Nothing was sent back to the application: a redirect URI this tenant has not "
            "registered is never redirected to.</p>"
        ),
    )


def _redirect(
    redirect_uri: str, response_mode: str, params: dict[str, str]
) -> Response:
    """Deliver `params` to the client the way it asked: query, fragment, or an auto-posted form."""
    if response_mode == "form_post":
        inputs = "".join(
            f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
            for k, v in params.items()
        )
        return HTMLResponse(
            "<!doctype html><html><body onload=\"document.forms[0].submit()\">"
            f'<form method="post" action="{html.escape(redirect_uri)}">{inputs}'
            "<noscript><button>Continue</button></noscript></form></body></html>"
        )
    encoded = urlencode(params)
    if response_mode == "fragment":
        return RedirectResponse(f"{redirect_uri}#{encoded}", status_code=302)
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}{encoded}", status_code=302)


def _error_redirect(pending: AuthorizeRequest, error: OAuthError) -> Response:
    params = {"error": error.error, "error_description": error.description}
    if pending.state is not None:
        params["state"] = pending.state
    return _redirect(pending.redirect_uri, pending.response_mode, params)


def _session_cookie(tenant: str) -> str:
    return f"mock_entra_session_{re.sub(r'[^A-Za-z0-9_-]', '_', tenant)}"


def _issue_code(pending: AuthorizeRequest, identity: Identity) -> Response:
    code = secrets.token_urlsafe(32)
    _codes[code] = Grant(
        tenant=pending.tenant,
        client_id=pending.client_id,
        identity=identity,
        scopes=pending.scopes,
        resource=pending.resource,
        expires=time.time() + CODE_TTL,
        redirect_uri=pending.redirect_uri,
        code_challenge=pending.code_challenge,
        nonce=pending.nonce,
    )
    params = {"code": code}
    if pending.client_info:
        params["client_info"] = client_info(identity, pending.tenant)
    if pending.state is not None:
        params["state"] = pending.state
    params["session_state"] = secrets.token_hex(16)
    return _redirect(pending.redirect_uri, pending.response_mode, params)


def _validate_authorize(tenant: str, params: dict[str, str]) -> AuthorizeRequest | Response:
    """Validate an `/authorize` request: a trusted client and redirect URI first, then the rest.

    The order is the security property. Until the client and the redirect URI are known good,
    every error is a page here; only after both is an error *reported* by redirecting.
    """
    client_id = params.get("client_id", "")
    if client_id != settings.entra_spa_client_id:
        return _error_page(
            400,
            "Unknown application",
            f"AADSTS700016: Application with identifier {client_id!r} was not found in the "
            f"directory {tenant!r}. This mock tenant knows one SPA client: "
            f"{settings.entra_spa_client_id!r} (MOCK_ENTRA_SPA_CLIENT_ID).",
        )
    redirect_uri = params.get("redirect_uri", "")
    if redirect_uri not in settings.entra_redirect_uris:
        return _error_page(
            400,
            "Redirect URI mismatch",
            f"AADSTS50011: The redirect URI {redirect_uri!r} specified in the request does not "
            "match the redirect URIs configured for the application. Registered: "
            f"{settings.entra_redirect_uris} (MOCK_ENTRA_REDIRECT_URIS).",
        )

    response_mode = params.get("response_mode", "query")
    pending = AuthorizeRequest(
        tenant=tenant,
        client_id=client_id,
        redirect_uri=redirect_uri,
        response_mode=response_mode if response_mode in ("query", "fragment", "form_post")
        else "query",
        state=params.get("state"),
        nonce=params.get("nonce"),
        scopes=[],
        resource=None,
        code_challenge=params.get("code_challenge", ""),
        client_info=params.get("client_info") == "1",
        created=time.time(),
    )
    try:
        if response_mode not in ("query", "fragment", "form_post"):
            raise OAuthError("invalid_request", f"unsupported response_mode {response_mode!r}")
        if params.get("response_type") != "code":
            raise OAuthError(
                "unsupported_response_type",
                "this mock tenant implements the authorization code flow only (response_type=code)",
            )
        if not pending.code_challenge:
            raise OAuthError(
                "invalid_request",
                "AADSTS9002325: Proof Key for Code Exchange is required for cross-origin "
                "authorization code redemption.",
            )
        if params.get("code_challenge_method") != "S256":
            raise OAuthError(
                "invalid_request",
                "code_challenge_method must be S256; this tenant does not accept plain PKCE",
            )
        pending.scopes, pending.resource = parse_scopes(params.get("scope", ""))
        if "openid" not in pending.scopes:
            raise OAuthError("invalid_scope", "a sign-in request must include the openid scope")
    except OAuthError as error:
        return _error_redirect(pending, error)
    return pending


@router.get("/{tenant}/oauth2/v2.0/authorize", response_class=HTMLResponse)
def authorize(tenant: str, request: Request) -> Response:
    """Start a sign-in: validate the request, then either SSO from the session or ask who.

    `prompt=none` is MSAL's hidden-iframe silent sign-in: answered from the session cookie or with
    `login_required`, never with a page. `prompt=login`/`select_account` always shows the page.
    With no prompt and a live session the code is issued straight away — what a real tenant does
    for a user who is already signed in, and what makes MSAL's second sign-in silent.
    """
    try:
        _require_enabled()
    except _Disabled:
        return _disabled()
    params = dict(request.query_params)
    validated = _validate_authorize(tenant, params)
    if not isinstance(validated, AuthorizeRequest):
        return validated
    pending = validated

    session = _sessions.get(request.cookies.get(_session_cookie(tenant), ""))
    prompt = params.get("prompt", "")
    if prompt == "none":
        if session is None:
            return _error_redirect(
                pending,
                OAuthError(
                    "login_required",
                    "AADSTS50058: A silent sign-in request was sent but no user is signed in.",
                ),
            )
        return _issue_code(pending, session)
    if session is not None and prompt not in ("login", "select_account"):
        return _issue_code(pending, session)

    request_id = secrets.token_urlsafe(24)
    _pending[request_id] = pending
    return HTMLResponse(_login_page(tenant, request_id, params.get("login_hint", "")))


async def _form(request: Request) -> dict[str, str]:
    """An `application/x-www-form-urlencoded` body, without a multipart dependency for it."""
    body = (await request.body()).decode("utf-8")
    return {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}


@router.post("/{tenant}/oauth2/v2.0/authorize", response_class=HTMLResponse)
async def choose_identity(tenant: str, request: Request) -> Response:
    """The login page's answer: who the tester chose to be. Issues the code and the session."""
    try:
        _require_enabled()
    except _Disabled:
        return _disabled()
    form = await _form(request)
    pending = _pending.pop(form.get("request_id", ""), None)
    if pending is None or pending.tenant != tenant or time.time() - pending.created > PENDING_TTL:
        return _error_page(
            400,
            "Sign-in expired",
            "This sign-in request is unknown or has expired. Start again from the application.",
        )

    choice = form.get("user", "")
    if choice == "custom":
        oid = form.get("oid", "").strip()
        if not oid:
            _pending[form["request_id"]] = pending
            return _error_page(400, "No object id", "A custom identity needs an oid.")
        identity = Identity(
            key="custom",
            oid=oid,
            upn=form.get("upn", "").strip(),
            name=form.get("name", "").strip() or oid,
            roles=[role.strip() for role in form.get("roles", "").split(",") if role.strip()],
        )
    else:
        known = users().get(choice)
        if known is None:
            return _error_page(400, "Unknown user", f"No preset user named {choice!r}.")
        identity = known

    session_id = secrets.token_urlsafe(24)
    _sessions[session_id] = identity
    response = _issue_code(pending, identity)
    secure = request.url.scheme == "https"
    response.set_cookie(
        _session_cookie(tenant),
        session_id,
        path=f"/entra/{tenant}",
        httponly=True,
        secure=secure,
        # None (with Secure) so MSAL's hidden-iframe `prompt=none` sees it from the SPA's origin;
        # Lax on plain http, where None is refused outright.
        samesite="none" if secure else "lax",
    )
    return response


# --- /token ------------------------------------------------------------------------------------


def _token_error(request: Request, error: OAuthError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"error": error.error, "error_description": error.description},
        headers=cors_headers(request),
    )


def _verify_pkce(verifier: str, challenge: str) -> None:
    if not _VERIFIER.match(verifier):
        raise OAuthError(
            "invalid_grant",
            "AADSTS501481: The code_verifier is missing or is not a valid PKCE verifier "
            "(43-128 unreserved characters).",
        )
    if _b64url(hashlib.sha256(verifier.encode("ascii")).digest()) != challenge:
        raise OAuthError(
            "invalid_grant",
            "AADSTS501481: The Code_Verifier does not match the code_challenge supplied in the "
            "authorization request.",
        )


def _redeem_code(tenant: str, form: dict[str, str]) -> dict[str, object]:
    code = form.get("code", "")
    grant = _codes.get(code)
    if grant is None or grant.tenant != tenant:
        raise OAuthError("invalid_grant", "AADSTS9002313: The provided authorization code is invalid.")
    if grant.used:
        raise OAuthError(
            "invalid_grant", "AADSTS54005: OAuth2 Authorization code was already redeemed."
        )
    # Spent before any other check, so a failed redemption — a wrong verifier above all — burns
    # the code rather than leaving it open to another guess.
    grant.used = True
    if time.time() > grant.expires:
        raise OAuthError("invalid_grant", "AADSTS70008: The provided authorization code has expired.")
    if form.get("client_id") != grant.client_id:
        raise OAuthError(
            "invalid_grant", "AADSTS700005: The authorization code was issued to another client."
        )
    if form.get("redirect_uri") != grant.redirect_uri:
        raise OAuthError(
            "invalid_grant",
            "AADSTS50011: The redirect_uri does not match the one the authorization code was "
            "issued for.",
        )
    _verify_pkce(form.get("code_verifier", ""), grant.code_challenge)
    return issue_tokens(grant, nonce=grant.nonce)


def _refresh(tenant: str, form: dict[str, str]) -> dict[str, object]:
    grant = _refresh_tokens.get(form.get("refresh_token", ""))
    if grant is None or grant.tenant != tenant:
        raise OAuthError("invalid_grant", "AADSTS9002313: The refresh token is invalid.")
    if time.time() > grant.expires:
        raise OAuthError("invalid_grant", "AADSTS700084: The refresh token has expired.")
    if form.get("client_id") != grant.client_id:
        raise OAuthError(
            "invalid_grant", "AADSTS700005: The refresh token was issued to another client."
        )
    # A refresh may ask for a different resource scope than the sign-in did — that is how a SPA
    # gets a token for a second API — so the scope is re-parsed, not copied.
    scopes, resource = parse_scopes(form.get("scope", "") or " ".join(grant.scopes))
    refreshed = Grant(
        tenant=tenant,
        client_id=grant.client_id,
        identity=grant.identity,
        scopes=scopes if "offline_access" in scopes else [*scopes, "offline_access"],
        resource=resource,
        expires=grant.expires,
    )
    return issue_tokens(refreshed, nonce=None)


async def token_grant(tenant: str, request: Request) -> Response:
    """The form-encoded half of the token endpoint: `authorization_code` and `refresh_token`.

    Requires an `Origin` from a registered redirect URI, which is the SPA platform's rule in Entra
    — a SPA's code may only be redeemed cross-origin — and the reason MSAL's `fetch` works here
    and a `curl` replay of a stolen code does not.
    """
    try:
        _require_enabled()
    except _Disabled:
        return _disabled()
    origin = request.headers.get("origin", "")
    if not origin:
        return _token_error(
            request,
            OAuthError(
                "invalid_request",
                "AADSTS9002327: Tokens issued for the 'Single-Page Application' client-type may "
                "only be redeemed via cross-origin requests.",
            ),
        )
    if origin not in allowed_origins():
        return _token_error(
            request,
            OAuthError(
                "invalid_request",
                f"Origin {origin!r} is not the origin of any registered redirect URI.",
            ),
        )
    form = await _form(request)
    try:
        grant_type = form.get("grant_type", "")
        if grant_type == "authorization_code":
            body = _redeem_code(tenant, form)
        elif grant_type == "refresh_token":
            body = _refresh(tenant, form)
        else:
            raise OAuthError(
                "unsupported_grant_type",
                f"grant_type {grant_type!r}: this tenant serves authorization_code and "
                "refresh_token (and a JSON body for the test mint)",
            )
    except OAuthError as error:
        return _token_error(request, error)
    return JSONResponse(
        content=body,
        headers={**cors_headers(request), "Cache-Control": "no-store", "Pragma": "no-cache"},
    )


# --- /logout -----------------------------------------------------------------------------------


@router.get("/{tenant}/oauth2/v2.0/logout", response_class=HTMLResponse)
def logout(tenant: str, request: Request) -> Response:
    """End the tenant's session, then send the browser back if the target is registered.

    `post_logout_redirect_uri` is honoured when it is a registered redirect URI or the bare origin
    of one — MSAL's default is `window.location.origin` — and ignored otherwise, for the same
    open-redirect reason `/authorize` refuses an unregistered redirect URI.
    """
    cookie = _session_cookie(tenant)
    _sessions.pop(request.cookies.get(cookie, ""), None)
    target = request.query_params.get("post_logout_redirect_uri", "")
    registered = set(settings.entra_redirect_uris) | allowed_origins()
    if target and (target in registered or target.rstrip("/") in registered):
        state = request.query_params.get("state")
        if state:
            target = f"{target}{'&' if '?' in target else '?'}{urlencode({'state': state})}"
        response: Response = RedirectResponse(target, status_code=302)
    else:
        response = HTMLResponse(_page("<h1>Signed out</h1><p>You can close this window.</p>"))
    response.delete_cookie(cookie, path=f"/entra/{tenant}")
    return response


# --- the page ----------------------------------------------------------------------------------


def _page(body: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Mock tenant sign-in (TEST ONLY)</title><style>"
        "body{font-family:system-ui,sans-serif;max-width:34rem;margin:2rem auto;padding:0 1rem}"
        ".banner{background:#b00020;color:#fff;padding:.5rem .75rem;font-weight:600}"
        "button{display:block;width:100%;margin:.4rem 0;padding:.6rem;text-align:left;"
        "font-size:1rem;cursor:pointer}"
        "fieldset{margin-top:1.5rem}label{display:block;margin:.3rem 0}"
        "input[type=text]{width:100%}.err{color:#b00020}small{color:#555}"
        "</style></head><body>"
        "<p class=banner>MOCK ENTRA TENANT &mdash; TEST ONLY. Not a real identity provider: "
        "whoever you pick below is who you are.</p>"
        f"{body}</body></html>"
    )


def _login_page(tenant: str, request_id: str, login_hint: str) -> str:
    action = html.escape(f"/entra/{tenant}/oauth2/v2.0/authorize")
    rid = html.escape(request_id)
    buttons = "".join(
        f'<button type=submit name=user value="{html.escape(key)}" '
        f'data-testid="mock-login-{html.escape(key)}"'
        f"{' autofocus' if login_hint in (key, user.upn) else ''}>"
        f"<strong>{html.escape(user.name)}</strong> &lt;{html.escape(user.upn)}&gt;<br>"
        f"<small>oid {html.escape(user.oid)} &middot; roles: "
        f"{html.escape(', '.join(user.roles) or '(none)')}</small></button>"
        for key, user in users().items()
    )
    return _page(
        f"<h1>Sign in to {html.escape(tenant)}</h1>"
        f'<form method=post action="{action}">'
        f'<input type=hidden name=request_id value="{rid}">{buttons}</form>'
        f'<form method=post action="{action}"><fieldset><legend>Someone else</legend>'
        f'<input type=hidden name=request_id value="{rid}">'
        "<label>oid <input type=text name=oid required data-testid=mock-login-oid></label>"
        "<label>preferred_username <input type=text name=upn data-testid=mock-login-upn></label>"
        "<label>name <input type=text name=name data-testid=mock-login-name></label>"
        "<label>roles (comma-separated) <input type=text name=roles "
        "data-testid=mock-login-roles></label>"
        "<button type=submit name=user value=custom data-testid=mock-login-custom>"
        "Sign in as this identity</button></fieldset></form>"
    )
