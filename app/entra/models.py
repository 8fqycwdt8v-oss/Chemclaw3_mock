"""The token-request shape, and what makes it a *test* instrument rather than an IdP.

Every field but `oid` exists to mint a token that should be *refused*. A lane proving that
Chemclaw3 accepts a good token has proven half of authentication; the other half is that it turns
away a token minted for another resource, by another issuer, after its expiry, or with a key this
tenant never published — and each of those is one override here rather than a separate endpoint.
"""

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """What identity to mint, and which way to make it invalid if that is the point."""

    #: The Entra object id every backend action is attributed to. The one required field.
    oid: str = Field(min_length=1)
    #: `preferred_username`, which Chemclaw3 reads into `Principal.upn`.
    upn: str = ""
    #: App roles. Chemclaw3 gates expensive tools, write tools and the reviewer routes on these.
    roles: list[str] = Field(default_factory=list)
    #: Directory groups. Only reaches the role set when `CHEMCLAW_ENTRA_GROUP_CLAIMS_AS_ROLES` is
    #: on, and then namespaced with `group:` — the prefix that stops a group being read as a role.
    groups: list[str] = Field(default_factory=list)
    #: Seconds until expiry. **Negative mints an already-expired token**, which is how a lane
    #: proves the expiry check rather than waiting an hour for it.
    expires_in: int = 3600
    #: Override the `aud` claim to prove the confused-deputy guard: a token correctly signed by
    #: this tenant, for a *different* resource, must still be refused.
    audience: str = ""
    #: Override the `iss` claim, for the same reason one hop down.
    issuer: str = ""
    #: Sign with the key the JWKS does **not** publish — a forgery whose `kid` may still name a
    #: real key. Nothing about the token looks wrong until the signature is checked.
    unpublished_key: bool = False
    #: Omit `exp` entirely. Distinct from an expired token and not covered by it: a validator that
    #: only checks `exp` when present accepts a token that simply leaves it out, forever.
    omit_expiry: bool = False


class TokenResponse(BaseModel):
    """OAuth-shaped, so a caller reads it the way it reads a real token endpoint's answer."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
