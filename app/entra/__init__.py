"""A stand-in Entra ID tenant: it publishes signing keys and mints tokens Chemclaw3 accepts.

Chemclaw3's front door validates every request's bearer token against a tenant's JWKS, checking
the RS256 signature, the audience and the issuer. Everything about that is testable without
Microsoft — a tenant, to a resource server, *is* a JWKS document and an issuer string — and until
this existed nothing in the four-repo stack could run with `CHEMCLAW_ENTRA_REQUIRED=true`. The
live lane pinned it false, the UI e2e ran `AUTH_MODE=dev`, and the enforced path that every real
deployment runs was exercised by unit tests alone.

This is deliberately **not** an OAuth implementation. There is no authorization code flow, no
consent, no user database and no client authentication: a caller asks for a token naming whatever
identity and roles it wants, and gets one. That is the right shape for a mock — the thing under
test is the resource server, not the IdP — and it is why nothing here may ever be reachable from
somewhere that matters.
"""
