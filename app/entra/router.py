"""The tenant's HTTP surface: discovery, the published keys, a token mint, and the controls.

Only the keys route is what Chemclaw3 actually calls at runtime — its front door fetches the JWKS
and nothing else. Discovery is here because it costs four lines and it is what a human reaches for
when they want to know whether the thing is wired up. The mint is for whoever is driving the test:
a shell script, a Playwright fixture, `make live-probes`.

The two `_control` routes are for the same driver, and they are what lets a lane exercise the
*failure* paths as well as the happy one: break the keys endpoint, or rotate the signing key. They
are underscore-prefixed because no real tenant serves them, and gated by their own switch — see
`app/entra/faults.py` for why that is a second switch rather than part of `MOCK_ENTRA_ENABLED`.

**Unauthenticated, and it hands out any identity asked for.** That is the correct shape for this
process and the reason `MOCK_ENTRA_ENABLED` defaults to *off*: reachable from anywhere that
matters, it is a machine for forging credentials against whatever resource server trusts it.
"""

import time

import jwt
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

from app.config import settings
from app.entra import faults, keys
from app.entra.models import JwksFaultRequest, TenantState, TokenRequest, TokenResponse

router = APIRouter(prefix="/entra", tags=["entra"])


def _issuer() -> str:
    """The `iss` this tenant claims, and the value Chemclaw3's `CHEMCLAW_ENTRA_ISSUER` must match."""
    return settings.entra_issuer


@router.get("/{tenant}/v2.0/.well-known/openid-configuration")
def discovery(tenant: str) -> dict[str, object]:
    """The discovery document, so `curl`ing the base URL tells a human what is wired up.

    Chemclaw3 does not read this — it derives the JWKS and issuer from its own settings — so this
    is documentation served over HTTP rather than a contract anything depends on.
    """
    base = _issuer().removesuffix("/v2.0")
    return {
        "issuer": _issuer(),
        "jwks_uri": f"{base}/discovery/v2.0/keys",
        "token_endpoint": f"{base}/oauth2/v2.0/token",
        "id_token_signing_alg_values_supported": ["RS256"],
        "note": f"mock tenant {tenant!r} — no authorization flow, no client authentication",
    }


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


@router.post("/{tenant}/oauth2/v2.0/token", response_model=TokenResponse)
def mint(tenant: str, request: TokenRequest) -> TokenResponse:
    """Mint an access token for the identity asked for — valid, or invalid in one stated way.

    No client authentication and no flow: see the module docstring for why that is right here and
    why this surface is off by default.
    """
    if not settings.entra_enabled:
        raise HTTPException(status_code=404, detail="mock entra tenant is disabled")

    claims: dict[str, object] = {
        "aud": request.audience or settings.entra_audience,
        "iss": request.issuer or _issuer(),
        "iat": int(time.time()),
        "oid": request.oid,
        "tid": tenant,
    }
    if not request.omit_expiry:
        claims["exp"] = int(time.time()) + request.expires_in
    if request.upn:
        claims["preferred_username"] = request.upn
    if request.roles:
        claims["roles"] = request.roles
    if request.groups:
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
