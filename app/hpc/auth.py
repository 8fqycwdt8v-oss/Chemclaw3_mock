"""Bearer-token auth for the mock launcher and artifact store.

Mirrors the real client's two token seams (`workflows/hpc/nextflow.py`): the launcher checks
`hpc_api_token`; the artifact store checks its own `hpc_artifact_store_token` when configured,
but — since this mock serves both endpoints from the same origin — also accepts the launcher
token, because that is what the real client sends to a same-origin artifact store when no
separate artifact token is configured (`_artifact_headers`'s same-origin fallback).
"""

from hmac import compare_digest

from fastapi import Header, HTTPException, status

from app.config import settings


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[len("bearer ") :].strip()


def _matches(presented: str | None, expected: str) -> bool:
    """Whether `presented` is `expected`, compared in constant time.

    `compare_digest` rather than `!=`, and on *bytes* rather than `str` — it raises `TypeError`
    when either `str` operand is non-ASCII, which would turn an auth boundary into a 500 that any
    caller could produce at will. The real path this file mirrors
    (`Chemclaw3/connectors/server.py`) makes both moves for exactly those reasons; a mock whose
    docstring claims to mirror the real seams should not be the one place that does not.

    An absent credential is refused without comparing, so a missing token cannot be measured
    against the empty string.
    """
    if not presented or not expected:
        return False
    return compare_digest(
        presented.encode("utf-8", "surrogateescape"), expected.encode("utf-8", "surrogateescape")
    )


def require_launcher_auth(authorization: str | None = Header(default=None)) -> None:
    if not settings.hpc_enforce_auth:
        return
    if not _matches(_bearer_token(authorization), settings.hpc_api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid Authorization bearer token",
        )


def require_artifact_auth(authorization: str | None = Header(default=None)) -> None:
    if not settings.hpc_enforce_auth:
        return
    expected = settings.hpc_artifact_store_token or settings.hpc_api_token
    if not _matches(_bearer_token(authorization), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid Authorization bearer token",
        )
