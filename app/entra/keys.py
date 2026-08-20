"""The tenant's signing keys: one published, one deliberately not.

Two keys rather than one, because half of what a lane needs to prove about authentication is what
gets *refused*. A token signed by `unpublished` is indistinguishable from a real one except that
its key is absent from the JWKS, which is exactly the forgery a resource server must reject — and
a mock that can only mint valid tokens cannot ask that question.

Keys are generated once at import and live in memory. They are regenerated on every restart, which
is correct for a mock: a signing key that survives in a repository is a signing key that eventually
signs something real. A lane that needs stability across restarts pins `MOCK_ENTRA_PRIVATE_KEY_PEM`.
"""

import base64
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings

#: The `kid` of the key the JWKS publishes, and of the one it does not.
PUBLISHED_KID = "mock-entra-key-1"
UNPUBLISHED_KID = "mock-entra-key-unpublished"


def _load_or_generate(pem: str) -> Any:
    """The configured private key, or a fresh 2048-bit one when none is configured."""
    if pem.strip():
        return serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


_PUBLISHED = _load_or_generate(settings.entra_private_key_pem)
_UNPUBLISHED = rsa.generate_private_key(public_exponent=65537, key_size=2048)

_KEYS: dict[str, Any] = {PUBLISHED_KID: _PUBLISHED, UNPUBLISHED_KID: _UNPUBLISHED}


def private_pem(kid: str) -> bytes:
    """The PKCS#8 PEM for `kid`, as PyJWT wants it for signing."""
    return _KEYS[kid].private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _b64u(value: int) -> str:
    """One RSA parameter as the unpadded base64url a JWK spells it with."""
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def jwks() -> dict[str, list[dict[str, str]]]:
    """The published key set — the document a resource server fetches to verify a signature.

    One key. `UNPUBLISHED_KID` is absent on purpose and that absence is the feature: it is what
    makes "reject a token whose signing key this tenant never vouched for" a thing a lane can
    actually test rather than assert.
    """
    numbers = _PUBLISHED.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": PUBLISHED_KID,
                "n": _b64u(numbers.n),
                "e": _b64u(numbers.e),
            }
        ]
    }
