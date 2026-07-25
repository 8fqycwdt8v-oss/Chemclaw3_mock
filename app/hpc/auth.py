"""Bearer-token auth for the mock launcher and artifact store.

Mirrors the real client's two token seams (`workflows/hpc/nextflow.py`): the launcher checks
`hpc_api_token`; the artifact store checks its own `hpc_artifact_store_token` when configured,
but — since this mock serves both endpoints from the same origin — also accepts the launcher
token, because that is what the real client sends to a same-origin artifact store when no
separate artifact token is configured (`_artifact_headers`'s same-origin fallback).
"""

from fastapi import Header, HTTPException, status

from app.config import settings


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[len("bearer ") :].strip()


def require_launcher_auth(authorization: str | None = Header(default=None)) -> None:
    if not settings.hpc_enforce_auth:
        return
    token = _bearer_token(authorization)
    if token != settings.hpc_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid Authorization bearer token",
        )


def require_artifact_auth(authorization: str | None = Header(default=None)) -> None:
    if not settings.hpc_enforce_auth:
        return
    token = _bearer_token(authorization)
    expected = settings.hpc_artifact_store_token or settings.hpc_api_token
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid Authorization bearer token",
        )
