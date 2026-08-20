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

        # Caps each real HTE dataset (app/eln/real_hte.py) to its first N rows when set to a
        # positive number -- real data only truncated, never fabricated. 0 (default) seeds every
        # real record. Tests override this to a small number to keep the suite fast.
        self.hte_max_records_per_dataset = _env_int("MOCK_HTE_MAX_RECORDS_PER_DATASET", 0)

        # A stand-in Entra tenant (app/entra/): publishes signing keys and mints tokens that
        # Chemclaw3's front door accepts, so a lane can run with CHEMCLAW_ENTRA_REQUIRED=true.
        #
        # **Off by default, and that default is the security control.** The mint endpoint takes no
        # client authentication and issues a token for whatever identity and roles are asked for,
        # so anywhere it is reachable, it is a machine for forging credentials against every
        # resource server that trusts this issuer. Nothing else in this process is dangerous when
        # left on; this is, so it is opt-in per run rather than per deployment.
        self.entra_enabled = _env_bool("MOCK_ENTRA_ENABLED", False)
        # The `iss` this tenant claims. Chemclaw3's CHEMCLAW_ENTRA_ISSUER must match it exactly,
        # and its CHEMCLAW_ENTRA_JWKS_URL must point at this tenant's keys route — the two derive
        # independently there, which is why both are set rather than a tenant id.
        self.entra_issuer = _env_str(
            "MOCK_ENTRA_ISSUER", "http://127.0.0.1:8090/entra/mock-tenant/v2.0"
        )
        # The `aud` minted tokens carry. Must equal Chemclaw3's CHEMCLAW_ENTRA_AUDIENCE, which is
        # the confused-deputy guard: a token for another resource is refused even when this tenant
        # signed it.
        self.entra_audience = _env_str("MOCK_ENTRA_AUDIENCE", "api://chemclaw")
        # A fixed signing key, for a lane that needs tokens to survive a restart of this process.
        # Empty (the default) generates one per start, which is what a mock should do: a signing
        # key committed to a repository is one that eventually signs something real.
        self.entra_private_key_pem = _env_str("MOCK_ENTRA_PRIVATE_KEY_PEM", "")

        # MCP vendor tool server (run standalone, see app/mcp_tools/vendor_server.py).
        self.mcp_vendor_host = _env_str("MOCK_MCP_VENDOR_HOST", "0.0.0.0")
        self.mcp_vendor_port = _env_int("MOCK_MCP_VENDOR_PORT", 8091)


settings = Settings()
