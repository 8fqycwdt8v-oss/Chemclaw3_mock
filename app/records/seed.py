"""Writes the LIMS and HTE plate exports where Chemclaw3's record-drop sources read them.

Chemclaw3's `lims-json` and `hte-json` sources read `<CHEMCLAW_RECORD_EXPORT_DIR>/lims` and
`.../hte` off disk, so the mock's job is to write files under `MOCK_RECORD_EXPORT_DIR`, meant to be
the same path. Re-seeding clears the previous `*.json` files first, so it is idempotent.
"""

import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.records.hte_plates import hte_plate_exports
from app.records.lims import lims_exports

# The subdirectory each source's manifest names in its `config: {path: ...}`.
LIMS_SUBDIR = "lims"
HTE_SUBDIR = "hte"


def _write_all(directory: Path, exports: list[dict[str, Any]]) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    for existing in directory.glob("*.json"):
        existing.unlink()
    for export in exports:
        (directory / f"{export['id']}.json").write_text(
            json.dumps(export, indent=2), "utf-8"
        )
    return len(exports)


def seed_records() -> dict[str, int]:
    """Write both exports; return how many files each directory now holds."""
    root = settings.record_export_dir
    return {
        "lims": _write_all(root / LIMS_SUBDIR, lims_exports()),
        "hte": _write_all(root / HTE_SUBDIR, hte_plate_exports()),
    }
