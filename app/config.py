"""Env-driven settings for the mock backend itself.

Deliberately separate from Chemclaw3's own `CHEMCLAW_*` settings: this process is a stand-in
for Chemclaw3's external dependencies, not a Chemclaw3 process, so it reads its own `MOCK_*`
variables. Chemclaw3 is pointed at this server's URLs via its own `CHEMCLAW_HPC_API_BASE_URL` /
`CHEMCLAW_ELN_EXPORT_DIR` / etc. — see README.md for the exact wiring.
"""

import os
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    """All configuration for the mock HPC + ELN + MCP backend, read once at import time."""

    def __init__(self) -> None:
        # HPC launcher mock.
        self.hpc_api_token = _env_str("MOCK_HPC_API_TOKEN", "mock-hpc-token")
        self.hpc_artifact_store_token = _env_str("MOCK_HPC_ARTIFACT_STORE_TOKEN", "")
        self.hpc_enforce_auth = _env_bool("MOCK_HPC_ENFORCE_AUTH", True)
        self.hpc_polls_until_done = _env_int("MOCK_HPC_POLLS_UNTIL_DONE", 2)
        self.hpc_unknown_status_every_n_polls = _env_int("MOCK_HPC_UNKNOWN_STATUS_EVERY_N", 0)

        # ELN seeding: directories the seed writer materializes fixture files into. These are
        # meant to be set to the SAME paths Chemclaw3 is configured with
        # (CHEMCLAW_ELN_EXPORT_DIR / CHEMCLAW_ORD_EXPORT_DIR) — see README.md.
        self.eln_export_dir = Path(_env_str("MOCK_ELN_EXPORT_DIR", "./data/eln/exports"))
        self.ord_export_dir = Path(_env_str("MOCK_ORD_EXPORT_DIR", "./data/eln/exports/ord"))
        self.eln_seed_on_startup = _env_bool("MOCK_ELN_SEED_ON_STARTUP", True)

        # MCP vendor tool server (run standalone, see app/mcp_tools/vendor_server.py).
        self.mcp_vendor_host = _env_str("MOCK_MCP_VENDOR_HOST", "0.0.0.0")
        self.mcp_vendor_port = _env_int("MOCK_MCP_VENDOR_PORT", 8091)


settings = Settings()
