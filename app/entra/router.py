"""The tenant's HTTP surface: discovery, the published keys, and a token mint.

Three routes, and only the middle one is what Chemclaw3 actually calls at runtime — its front door
fetches the JWKS and nothing else. Discovery is here because it costs four lines and it is what a
human reaches for when they want to know whether the thing is wired up. The mint is for whoever is
driving the test: a shell script, a Playwright fixture, `make live-probes`.

**Unauthenticated, and it hands out any identity asked for.** That is the correct shape for this
process and the reason `MOCK_ENTRA_ENABLED` defaults to *off*: reachable from anywhere that
matters, it is a machine for forging credentials against whatever resource server trusts it.
"""

import time

import jwt
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.entra.keys import PUBLISHED_KID, UNPUBLISHED_KID, jwks, private_pem
from app.entra.models import TokenRequest, TokenResponse

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
def keys(tenant: str) -> dict[str, list[dict[str, str]]]:
    """The JWKS. **This is the one route Chemclaw3 itself calls**, once, and then caches.

    A resource server's entire relationship with a tenant is this document, which is why a mock
    tenant is a reasonable thing to build at all: there is nothing else to stand in for.
    """
    return jwks()


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

    kid = UNPUBLISHED_KID if request.unpublished_key else PUBLISHED_KID
    token = jwt.encode(claims, private_pem(kid), algorithm="RS256", headers={"kid": kid})
    return TokenResponse(access_token=token, expires_in=request.expires_in)
