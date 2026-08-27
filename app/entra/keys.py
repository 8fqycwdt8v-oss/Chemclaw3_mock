"""The tenant's signing keys: one published, one deliberately not.

Two keys rather than one, because half of what a lane needs to prove about authentication is what
gets *refused*. A token signed by `unpublished` is indistinguishable from a real one except that
its key is absent from the JWKS, which is exactly the forgery a resource server must reject — and
a mock that can only mint valid tokens cannot ask that question.

Keys are generated once at import and live in memory. They are regenerated on every restart, which
is correct for a mock: a signing key that survives in a repository is a signing key that eventually
signs something real. A lane that needs stability across restarts pins `MOCK_ENTRA_PRIVATE_KEY_PEM`.

The published set grows by exactly one operation: `rotate`, which is a *tenant* action rather than
a fault — a real tenant publishes its new key beside the old one so tokens minted a minute earlier
keep validating, and a resource server follows by refreshing the key set it holds. That is the
third behaviour Chemclaw3's `tests/test_entra_end_to_end.py` proves in-process and could not drive
here; it is reached through the same control surface as the faults, and gated by the same switch
(see `app/entra/faults.py`).
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

#: The published kids in the order the JWKS lists them, and the one `mint` signs with. Both move
#: only under `rotate`, so a process nobody has rotated behaves exactly as it did before rotation
#: existed.
_published: list[str] = [PUBLISHED_KID]
_signing_kid: str = PUBLISHED_KID


def signing_kid() -> str:
    """The `kid` a token minted now carries — the newest published key."""
    return _signing_kid


def rotate() -> str:
    """Publish a fresh signing key beside the current one, sign with it, and return its `kid`.

    Beside rather than instead of: a rotation that withdrew the old key would refuse every token
    already in flight, which is not what a tenant does and not the behaviour a resource server's
    bounded key-set refresh is written against.
    """
    global _signing_kid
    kid = f"mock-entra-key-{len(_published) + 1}"
    _KEYS[kid] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _published.append(kid)
    _signing_kid = kid
    return kid


def published_kids() -> list[str]:
    """Every `kid` the JWKS currently lists, oldest first."""
    return list(_published)


def reset() -> None:
    """Forget every rotation, back to the single key this process started with.

    No route does this — a tenant cannot un-rotate, and offering that would be modelling something
    real tenants do not do. It exists because the key set is module state that outlives a test, and
    the suite's fixtures have to put it back.
    """
    global _signing_kid
    for kid in _published[1:]:
        del _KEYS[kid]
    _published[:] = [PUBLISHED_KID]
    _signing_kid = PUBLISHED_KID


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


def _jwk(kid: str) -> dict[str, str]:
    """One published key, as a JWK."""
    numbers = _KEYS[kid].public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64u(numbers.n),
        "e": _b64u(numbers.e),
    }


def jwks() -> dict[str, list[dict[str, str]]]:
    """The published key set — the document a resource server fetches to verify a signature.

    One key until something rotates. `UNPUBLISHED_KID` is never in it and that absence is the
    feature: it is what makes "reject a token whose signing key this tenant never vouched for" a
    thing a lane can actually test rather than assert.
    """
    return {"keys": [_jwk(kid) for kid in _published]}
