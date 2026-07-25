"""Materializes the curated fixtures as flat files in the ELN export directories.

Chemclaw3's sync activity reads `*.json` files from `CHEMCLAW_ELN_EXPORT_DIR` /
`CHEMCLAW_ORD_EXPORT_DIR` directly off disk — there is no HTTP call for ELN data (see
`eln/json_adapter.py` / `eln/ord_adapter.py`). So this module's job is to write files into
whatever directories the mock is configured with (`MOCK_ELN_EXPORT_DIR` /
`MOCK_ORD_EXPORT_DIR`, meant to be the *same* paths Chemclaw3 is pointed at — see README.md),
not to serve them over HTTP. The HTTP router (`app/eln/router.py`) is a thin control surface on
top of this for inspection/testing: list what's on disk, append one new timestamped entry to
simulate live ELN activity (exercises the sync's `since`-cursor), and reset/reseed.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import settings
from app.eln.fixtures_data import ord_style_records, uspto_style_records

_JSON_INDENT = 2


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=_JSON_INDENT), encoding="utf-8")


def _clear_dir(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for existing in directory.glob("*.json"):
        existing.unlink()


def seed_all(*, reset: bool = True) -> dict[str, int]:
    """Write every curated fixture into the configured export directories.

    `reset=True` (the default, used on app startup) clears any prior `*.json` files first, so
    re-running seeding is idempotent. `reset=False` layers the fixtures on top of whatever is
    already there (used by the reseed-without-losing-appends case, if ever needed).
    """
    if reset:
        _clear_dir(settings.eln_export_dir)
        _clear_dir(settings.ord_export_dir)
    else:
        settings.eln_export_dir.mkdir(parents=True, exist_ok=True)
        settings.ord_export_dir.mkdir(parents=True, exist_ok=True)

    uspto_records = uspto_style_records()
    for record in uspto_records:
        _write_json(settings.eln_export_dir / f"{record['id']}.json", record)

    ord_records = ord_style_records()
    for record in ord_records:
        _write_json(settings.ord_export_dir / f"{record['reactionId']}.json", record)

    return {"eln_json": len(uspto_records), "eln_ord": len(ord_records)}


def list_entries(directory: Path) -> list[dict[str, Any]]:
    """Read back every `*.json` file currently in `directory`, sorted by filename."""
    entries = []
    for path in sorted(directory.glob("*.json")):
        try:
            entries.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return entries


def _next_timestamp(directory: Path, *, timestamp_reader: Any) -> datetime:
    """One second after the newest entry currently on disk (or now, if the directory is empty)."""
    latest = None
    for entry in list_entries(directory):
        candidate = timestamp_reader(entry)
        if candidate is not None and (latest is None or candidate > latest):
            latest = candidate
    return (latest or datetime.now(tz=UTC)) + timedelta(seconds=1)


def append_uspto_entry(*, archetype_index: int = 0) -> dict[str, Any]:
    """Append one new USPTO-style entry stamped after every existing entry (tests cursor sync)."""
    records = uspto_style_records()
    template = records[archetype_index % len(records)]
    timestamp = _next_timestamp(
        settings.eln_export_dir,
        timestamp_reader=lambda e: _parse_iso(e.get("timestamp")),
    )
    seq = len(list(settings.eln_export_dir.glob("*.json"))) + 1
    entry = dict(template)
    entry["id"] = f"uspto-live-{seq:04d}"
    entry["timestamp"] = timestamp.isoformat().replace("+00:00", "Z")
    _write_json(settings.eln_export_dir / f"{entry['id']}.json", entry)
    return entry


def append_ord_entry(*, archetype_index: int = 0) -> dict[str, Any]:
    """Append one new ORD-style entry stamped after every existing entry (tests cursor sync)."""
    records = ord_style_records()
    template = records[archetype_index % len(records)]
    timestamp = _next_timestamp(
        settings.ord_export_dir,
        timestamp_reader=lambda e: _parse_iso(
            e.get("provenance", {}).get("recordCreated", {}).get("time", {}).get("value")
        ),
    )
    seq = len(list(settings.ord_export_dir.glob("*.json"))) + 1
    entry = json.loads(json.dumps(template))  # deep copy
    entry["reactionId"] = f"ord-live-{seq:04d}"
    entry["provenance"]["recordCreated"]["time"]["value"] = timestamp.isoformat().replace(
        "+00:00", "Z"
    )
    _write_json(settings.ord_export_dir / f"{entry['reactionId']}.json", entry)
    return entry


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
