"""The DuckDB warehouse fixture: the seeded ELN records as one queryable `reactions` view.

Chemclaw3's typed query tools are generated from a source's `query:` binding over a warehouse view
(its D-2026-10-21-a-source-is-queried-through-typed-generated-tools). This builds that view from
the files the seed wrote, so the warehouse and the ELN drop directories hold the same records and
an answer computed one way can be checked the other (`app/eln/source_eval.py`).

The file is rebuilt beside the target and moved over it, so a reader holding the old file open is
never handed a half-written one.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from app.config import settings
from app.eln.seed import list_entries

#: The view's columns, in order: the names a `query:` binding declares.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("record_id", "VARCHAR"),
    ("source", "VARCHAR"),
    ("recorded_at", "TIMESTAMPTZ"),
    ("project", "VARCHAR"),
    ("operator", "VARCHAR"),
    ("doi", "VARCHAR"),
    ("yield_percent", "DOUBLE"),
    ("temperature_c", "DOUBLE"),
    ("reactants", "VARCHAR[]"),
    ("reagents", "VARCHAR[]"),
    ("catalysts", "VARCHAR[]"),
    ("product", "VARCHAR"),
    ("outcome", "VARCHAR"),
    ("procedure", "VARCHAR"),
)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _ord_row(record: dict[str, Any]) -> tuple[Any, ...]:
    def by_role(role: str) -> list[str]:
        return [
            component["identifiers"][0]["value"]
            for reaction_input in record["inputs"].values()
            for component in reaction_input["components"]
            if component["reactionRole"] == role
        ]

    product = record["outcomes"][0]["products"][0]
    yields = [
        m["percentage"]["value"] for m in product.get("measurements", []) if m["type"] == "YIELD"
    ]
    setpoint = record.get("conditions", {}).get("temperature", {}).get("setpoint")
    provenance = record["provenance"]
    return (
        record["reactionId"],
        "eln-ord",
        _timestamp(provenance["recordCreated"]["time"]["value"]),
        None,
        provenance["recordCreated"].get("person", {}).get("name"),
        provenance.get("doi"),
        float(yields[0]) if yields else None,
        float(setpoint["value"]) if setpoint else None,
        by_role("REACTANT"),
        by_role("REAGENT"),
        by_role("CATALYST"),
        product["identifiers"][0]["value"],
        None,
        record.get("notes", {}).get("procedureDetails"),
    )


def _free_text_row(record: dict[str, Any]) -> tuple[Any, ...]:
    def by_role(role: str) -> list[str]:
        return [r["smiles"] for r in record["reactants"] if r["role"] == role]

    product = record["products"][0]
    return (
        record["id"],
        "eln-json",
        _timestamp(record["timestamp"]),
        record.get("project"),
        record.get("operator"),
        None,
        product.get("yield_percent"),
        record.get("temperature_c"),
        by_role("reactant"),
        by_role("reagent"),
        by_role("catalyst"),
        product["smiles"],
        record.get("outcome"),
        record.get("procedure"),
    )


def build_warehouse(path: Path) -> int:
    """Rebuild the warehouse at `path` from the seeded export directories; return its row count."""
    rows = [_ord_row(r) for r in list_entries(settings.ord_export_dir)]
    rows += [_free_text_row(r) for r in list_entries(settings.eln_export_dir)]
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".building")
    staging.unlink(missing_ok=True)
    with duckdb.connect(str(staging)) as connection:
        columns = ", ".join(f"{name} {kind}" for name, kind in COLUMNS)
        connection.execute(f"CREATE TABLE reaction_rows ({columns})")
        placeholders = ", ".join("?" for _ in COLUMNS)
        connection.executemany(f"INSERT INTO reaction_rows VALUES ({placeholders})", rows)
        connection.execute("CREATE VIEW reactions AS SELECT * FROM reaction_rows")
    os.replace(staging, path)
    return len(rows)
