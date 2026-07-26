#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ELN export dirs — must be absolute so Chemclaw3 can point at the same paths
export MOCK_ELN_EXPORT_DIR="${MOCK_ELN_EXPORT_DIR:-$SCRIPT_DIR/data/eln/exports}"
export MOCK_ORD_EXPORT_DIR="${MOCK_ORD_EXPORT_DIR:-$SCRIPT_DIR/data/eln/exports/ord}"
export MOCK_HPC_API_TOKEN="${MOCK_HPC_API_TOKEN:-mock-hpc-token}"
export MOCK_HPC_ENFORCE_AUTH="${MOCK_HPC_ENFORCE_AUTH:-true}"
export MOCK_HPC_POLLS_UNTIL_DONE="${MOCK_HPC_POLLS_UNTIL_DONE:-2}"
export MOCK_ELN_SEED_ON_STARTUP="${MOCK_ELN_SEED_ON_STARTUP:-true}"

PORT="${MOCK_SERVER_PORT:-8090}"

mkdir -p "$MOCK_ELN_EXPORT_DIR" "$MOCK_ORD_EXPORT_DIR"

echo "Starting Chemclaw3 Mock backend on port $PORT"
echo "  ELN exports : $MOCK_ELN_EXPORT_DIR"
echo "  ORD exports : $MOCK_ORD_EXPORT_DIR"

exec "$SCRIPT_DIR/.venv/bin/python" -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info
