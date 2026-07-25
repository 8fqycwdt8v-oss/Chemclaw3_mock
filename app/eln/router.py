"""Inspection/control surface over the seeded ELN export directories.

Not part of Chemclaw3's real ingestion path (that reads the files directly off disk — see
`app/eln/seed.py`); this is for driving the mock during testing: see what's been seeded, drop in
one new timestamped entry to simulate live ELN activity, or reset back to the curated fixture
set.
"""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.eln.seed import append_ord_entry, append_uspto_entry, list_entries, seed_all

router = APIRouter(prefix="/eln")

_SourceName = Literal["json", "ord"]


def _directory(source: _SourceName):
    return settings.eln_export_dir if source == "json" else settings.ord_export_dir


@router.get("/{source}/entries")
def get_entries(source: _SourceName) -> list[dict[str, Any]]:
    return list_entries(_directory(source))


@router.post("/{source}/entries", status_code=status.HTTP_201_CREATED)
def add_entry(source: _SourceName, archetype_index: int = 0) -> dict[str, Any]:
    if source == "json":
        return append_uspto_entry(archetype_index=archetype_index)
    return append_ord_entry(archetype_index=archetype_index)


@router.post("/reset")
def reset() -> dict[str, int]:
    return seed_all(reset=True)


@router.get("/{source}/entries/{entry_id}")
def get_entry(source: _SourceName, entry_id: str) -> dict[str, Any]:
    for entry in list_entries(_directory(source)):
        current_id = entry.get("id") or entry.get("reactionId")
        if current_id == entry_id:
            return entry
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entry not found")
