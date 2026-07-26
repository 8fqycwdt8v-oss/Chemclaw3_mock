#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export MOCK_MCP_VENDOR_HOST="${MOCK_MCP_VENDOR_HOST:-0.0.0.0}"
export MOCK_MCP_VENDOR_PORT="${MOCK_MCP_VENDOR_PORT:-8091}"

echo "Starting Chemclaw3 Mock MCP vendor server on ${MOCK_MCP_VENDOR_HOST}:${MOCK_MCP_VENDOR_PORT}"

exec "$SCRIPT_DIR/.venv/bin/python" -m app.mcp_tools.vendor_server
