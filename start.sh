#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ELN export dirs — must be absolute so Chemclaw3 can point at the same paths
export MOCK_ELN_EXPORT_DIR="${MOCK_ELN_EXPORT_DIR:-$SCRIPT_DIR/data/eln/exports}"
export MOCK_ORD_EXPORT_DIR="${MOCK_ORD_EXPORT_DIR:-$SCRIPT_DIR/data/eln/exports/ord}"
export MOCK_ELN_SEED_ON_STARTUP="${MOCK_ELN_SEED_ON_STARTUP:-true}"

PORT="${MOCK_SERVER_PORT:-8090}"

mkdir -p "$MOCK_ELN_EXPORT_DIR" "$MOCK_ORD_EXPORT_DIR"

echo "Starting Chemclaw3 Mock backend on port $PORT"
echo "  ELN exports : $MOCK_ELN_EXPORT_DIR"
echo "  ORD exports : $MOCK_ORD_EXPORT_DIR"

# Optional TLS, for the stand-in tenant's browser sign-in: MSAL.js refuses an authority that is
# not https (loopback included), so a UI signing in against this process needs it served over TLS.
# Both or neither; a throwaway self-signed pair is enough (README.md, "Browser sign-in").
TLS_ARGS=()
if [[ -n "${MOCK_SSL_CERTFILE:-}" || -n "${MOCK_SSL_KEYFILE:-}" ]]; then
  : "${MOCK_SSL_CERTFILE:?MOCK_SSL_KEYFILE is set, so MOCK_SSL_CERTFILE must be too}"
  : "${MOCK_SSL_KEYFILE:?MOCK_SSL_CERTFILE is set, so MOCK_SSL_KEYFILE must be too}"
  TLS_ARGS=(--ssl-certfile "$MOCK_SSL_CERTFILE" --ssl-keyfile "$MOCK_SSL_KEYFILE")
  echo "  TLS         : $MOCK_SSL_CERTFILE"
fi

exec "$SCRIPT_DIR/.venv/bin/python" -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info \
  ${TLS_ARGS[@]+"${TLS_ARGS[@]}"}
