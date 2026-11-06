"""An HTE plate export built from real screens, in Chemclaw3's record-drop shape.

One file per plate, `{"id", "timestamp", "records": [plate]}`; the plate is what Chemclaw3's
`plate` kind validates (`ingest/records/kinds/plate.py`): its format, when it ran, and every well
with its factor levels and its run in the JSON-ELN shape. The wells are the real Santanilla et al.
1536-well screens (Science 2015, DOI 10.1126/science.1259203, Experiment 2) the ORD drop already
seeds as single reactions (`app/eln/real_hte.py`), at their real plate positions and yields — the
same runs seen from the HTE platform, so a lane enabling both sources holds each run twice, once
per source.
"""

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parents[1] / "eln" / "real_data"
_PLATE_FORMAT = 1536
_DOI = "10.1126/science.1259203"

# (plate id, CSV, title, when it ran): the two screens, one physical plate region each.
_PLATES = (
    (
        "SANTANILLA-AMIDATION",
        "santanilla_amidation_screen.csv",
        "3-bromopyridine + benzamide: 16 precatalysts x 6 bases",
        datetime(2023, 5, 1, 9, 0, tzinfo=UTC),
    ),
    (
        "SANTANILLA-SULFONAMIDATION",
        "santanilla_sulfonamidation_screen.csv",
        "3-bromopyridine + benzenesulfonamide: 16 precatalysts x 6 bases",
        datetime(2023, 5, 2, 9, 0, tzinfo=UTC),
    ),
)

# The screen ran 22 h at room temperature (the paper's quoted procedure).
_TIME_H = 22.0


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _well(row: dict[str, str], plate_id: str) -> dict[str, Any]:
    """One well: its real position, the factor levels it varied, and its run as JSON-ELN."""
    return {
        "well": row["plate_position"],
        "conditions": {"precatalyst": row["catalyst_name"], "base": row["base_name"]},
        "reaction": {
            "reactants": [
                {"smiles": row["aryl_halide_smiles"], "role": "reactant"},
                {"smiles": row["nucleophile_smiles"], "role": "reactant"},
                {"smiles": row["catalyst_smiles"], "role": "catalyst"},
                {"smiles": row["base_smiles"], "role": "reagent"},
            ],
            "products": [
                {
                    "smiles": row["product_smiles"],
                    "yield_percent": float(row["yield_percent"]),
                }
            ],
            "time_h": _TIME_H,
            "operator": f"hte-platform:{plate_id}",
            "procedure": f"Nanomole-scale 1536-well screen, 22 h at room temperature (DOI {_DOI}).",
        },
    }


def hte_plate_exports() -> list[dict[str, Any]]:
    """Every plate's export file, in run order."""
    exports = []
    for plate_id, filename, title, run_at in _PLATES:
        with open(_DATA_DIR / filename, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        exports.append(
            {
                "id": plate_id,
                "timestamp": _iso(run_at.replace(hour=18)),
                "records": [
                    {
                        "plate_id": plate_id,
                        "plate_format": _PLATE_FORMAT,
                        "title": title,
                        "run_at": _iso(run_at),
                        "wells": [_well(row, plate_id) for row in rows],
                    }
                ],
            }
        )
    return exports
