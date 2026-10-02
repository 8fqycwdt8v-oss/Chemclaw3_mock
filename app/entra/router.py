"""The tenant's HTTP surface: discovery, the published keys, a token mint, and the controls.

Only the keys route is what Chemclaw3 actually calls at runtime — its front door fetches the JWKS
and nothing else. Discovery is here because it costs four lines and it is what a human reaches for
when they want to know whether the thing is wired up — and, since the browser sign-in in
`oidc.py`, what MSAL.js reads to find the authorize, token and logout endpoints. The mint is for
whoever is driving the test: a shell script, a Playwright fixture, `make live-probes`. The token
route serves both it (a JSON body) and the browser flow's grants (a form body).

The two `_control` routes are for the same driver, and they are what lets a lane exercise the
*failure* paths as well as the happy one: break the keys endpoint, or rotate the signing key. They
are underscore-prefixed because no real tenant serves them, and gated by their own switch — see
`app/entra/faults.py` for why that is a second switch rather than part of `MOCK_ENTRA_ENABLED`.

**Unauthenticated, and it hands out any identity asked for.** That is the correct shape for this
process and the reason `MOCK_ENTRA_ENABLED` defaults to *off*: reachable from anywhere that
matters, it is a machine for forging credentials against whatever resource server trusts it.
"""

import time

import json

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.config import settings
from app.entra import faults, keys, oidc
from app.entra.models import JwksFaultRequest, TenantState, TokenRequest, TokenResponse

router = APIRouter(prefix="/entra", tags=["entra"])


def _issuer() -> str:
    """The `iss` this tenant claims, and the value Chemclaw3's `CHEMCLAW_ENTRA_ISSUER` must match."""
    return settings.entra_issuer


@router.get("/{tenant}/v2.0/.well-known/openid-configuration")
def discovery(tenant: str, request: Request) -> JSONResponse:
    """The discovery document — which MSAL.js *does* read, so it has to be right.

    Chemclaw3 does not read this — it derives the JWKS and issuer from its own settings. The
    browser sign-in does: `@azure/msal-browser` fetches it (with `fetch`, hence the CORS headers)
    to find the authorize, token and end-session endpoints of whatever authority it was given. The
    endpoints are derived from `MOCK_ENTRA_ISSUER` rather than from the request, so the document
    names the address the tenant was told it lives at — which is what an `iss` has to match.
    """
    base = _issuer().removesuffix("/v2.0")
    document = {
        "issuer": _issuer(),
        "jwks_uri": f"{base}/discovery/v2.0/keys",
        "authorization_endpoint": f"{base}/oauth2/v2.0/authorize",
        "token_endpoint": f"{base}/oauth2/v2.0/token",
        "end_session_endpoint": f"{base}/oauth2/v2.0/logout",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query", "fragment", "form_post"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": sorted(oidc.OIDC_SCOPES),
        "subject_types_supported": ["pairwise"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "claims_supported": [
            "sub", "iss", "aud", "exp", "iat", "nbf", "nonce", "oid", "tid", "name",
            "preferred_username", "roles", "ver",
        ],
        "note": (
            f"MOCK tenant {tenant!r}, TEST ONLY: the login page issues any identity the tester "
            "picks; the token endpoint also accepts a JSON body that mints one directly"
        ),
    }
    return JSONResponse(content=document, headers=oidc.cors_headers(request))


@router.get("/{tenant}/discovery/v2.0/keys")
def published_keys(tenant: str) -> Response:
    """The JWKS. **This is the one route Chemclaw3 itself calls**, once, and then caches.

    A resource server's entire relationship with a tenant is this document, which is why a mock
    tenant is a reasonable thing to build at all: there is nothing else to stand in for — and why
    it is the one route a fault can be armed on. Unarmed, this is the key set and nothing else.

    Each fault is served as the *wire shape* it stands for rather than as an error the caller can
    read: an outage is a 5xx (which `urllib`, and therefore PyJWT's JWKS client, raises as a
    connection error), and the other two are a 200 whose body is not a key set. Chemclaw3 turns all
    three into one 503, and the reason it can is that they fail in two different libraries.
    """
    fault = faults.armed()
    if fault == "unavailable":
        return JSONResponse(status_code=503, content={"error": "mock entra tenant is unavailable"})
    if fault == "malformed":
        return Response(content=faults.MALFORMED_BODY, media_type="text/html")
    if fault == "not_a_key_set":
        return Response(content=faults.NOT_A_KEY_SET_BODY, media_type="application/json")
    return JSONResponse(content=keys.jwks())


@router.options("/{tenant}/oauth2/v2.0/token", include_in_schema=False)
def token_preflight(tenant: str, request: Request) -> Response:
    """The CORS preflight MSAL's token `fetch` triggers. See `oidc.preflight`."""
    return oidc.preflight(request)


@router.post("/{tenant}/oauth2/v2.0/token", response_model=TokenResponse)
async def token(tenant: str, request: Request) -> Response | TokenResponse:
    """One URL, two callers, told apart by the body — as a real token endpoint is told by grant.

    A form-encoded body is OAuth: the browser sign-in redeeming a code or a refresh token
    (`app/entra/oidc.py`). A JSON body is the test mint below, unchanged — the shape every lane
    driver already posts, so adding the browser flow moved none of them.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/x-www-form-urlencoded"):
        return await oidc.token_grant(tenant, request)
    try:
        body = TokenRequest.model_validate(json.loads(await request.body() or b"null"))
    except (ValueError, ValidationError) as exc:
        errors = exc.errors() if isinstance(exc, ValidationError) else [
            {"type": "json_invalid", "loc": ("body",), "msg": str(exc), "input": None}
        ]
        raise RequestValidationError(errors) from exc
    return mint(tenant, body)


def mint(tenant: str, request: TokenRequest) -> TokenResponse:
    """Mint an access token for the identity asked for — valid, or invalid in one stated way.

    No client authentication and no flow: see the module docstring for why that is right here and
    why this surface is off by default.
    """
    if not settings.entra_enabled:
        raise HTTPException(status_code=404, detail="mock entra tenant is disabled")

    issued_at = int(time.time())
    claims: dict[str, object] = {
        "aud": request.audience or settings.entra_audience,
        "iss": request.issuer or _issuer(),
        "iat": issued_at,
        # Real Entra sets `nbf` on every token it issues, so this one does too. Nothing on the
        # reading side forces it — Chemclaw3 requires only `exp` — which is exactly why it belongs
        # here: a mock is worth what it is faithful about, and a claim omitted because no validator
        # happens to demand it is a difference between this token and the real one that every green
        # lane run would keep quiet about.
        "nbf": issued_at,
        "oid": request.oid,
        "tid": tenant,
    }
    if not request.omit_expiry:
        claims["exp"] = int(time.time()) + request.expires_in
    if request.upn:
        claims["preferred_username"] = request.upn
    if request.roles:
        claims["roles"] = request.roles
    if request.group_overage:
        # The overage: `groups` is *replaced*, which is the whole shape. `src1` and the
        # `getMemberObjects` endpoint are what a real token carries, and the endpoint is a Graph
        # call — one this mock does not serve and Chemclaw3 does not make (D-089 forbids it), so
        # what a lane proves here is that an overage is recognised, not that it is resolved.
        claims["_claim_names"] = {"groups": "src1"}
        claims["_claim_sources"] = {
            "src1": {
                "endpoint": (
                    f"https://graph.windows.net/{tenant}/users/{request.oid}/getMemberObjects"
                )
            }
        }
    elif request.groups:
        claims["groups"] = request.groups

    kid = keys.UNPUBLISHED_KID if request.unpublished_key else keys.signing_kid()
    token = jwt.encode(claims, keys.private_pem(kid), algorithm="RS256", headers={"kid": kid})
    return TokenResponse(access_token=token, expires_in=request.expires_in)


def _state() -> TenantState:
    """What the tenant is doing right now — the answer both control routes give."""
    return TenantState(
        jwks_fault=faults.armed(),
        signing_kid=keys.signing_kid(),
        published_kids=keys.published_kids(),
    )


def _require_fault_injection() -> None:
    """Refuse unless this run asked for the controls, naming the switch that turns them on.

    A 404 rather than a 403, matching the mint: there is no credential that would make this work,
    so "this route does not exist here" is the true answer. It names `MOCK_ENTRA_FAULT_INJECTION`
    because a control that is merely absent reads as a broken URL, and the next thing a driver does
    about a broken URL is guess at other ones.
    """
    if not settings.entra_fault_injection:
        raise HTTPException(
            status_code=404,
            detail=(
                "fault injection is disabled; start this process with "
                "MOCK_ENTRA_FAULT_INJECTION=true"
            ),
        )


@router.post("/{tenant}/_control/jwks-fault", response_model=TenantState)
def arm_jwks_fault(tenant: str, request: JwksFaultRequest) -> TenantState:
    """Make the keys endpoint serve `fault` until something says otherwise (`none` restores it).

    Sticky rather than one-shot: a resource server caches its key set, so "the next fetch fails" is
    not a state a caller can reason about — the question a lane asks is whether the front door is
    still 503ing while the tenant is down, and that needs the tenant to stay down.
    """
    _require_fault_injection()
    faults.arm(request.fault)
    return _state()


@router.post("/{tenant}/_control/rotate-signing-key", response_model=TenantState)
def rotate_signing_key(tenant: str) -> TenantState:
    """Publish a new signing key beside the current one and mint with it from now on.

    Not a fault — this is what a tenant legitimately does — but it is behind the same switch,
    because a rotation nobody expects is indistinguishable from an outage to whoever is holding a
    cached key set.
    """
    _require_fault_injection()
    keys.rotate()
    return _state()
