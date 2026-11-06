"""The LIMS and HTE plate drops: the shape Chemclaw3's record kinds read, seeded deterministically.

Pinned here: every file is one entry (`id`, `timestamp`, `records`); LIMS rows carry what the
`measurement` kind requires, with a stability series whose rise is known; plate wells sit at real
positions of a 1536-well plate, once each, with the published yields; and the startup seed writes
both drops where Chemclaw3's `lims-json` and `hte-json` sources look.
"""

import csv
import json
from datetime import datetime
from itertools import pairwise
from pathlib import Path

import pytest

from app.config import settings
from app.records.hte_plates import hte_plate_exports
from app.records.lims import IMPURITY_RISE_PER_MONTH, lims_exports
from app.records.seed import HTE_SUBDIR, LIMS_SUBDIR, seed_records

_REAL_DATA = Path(__file__).resolve().parents[1] / "app" / "eln" / "real_data"
# The unit spellings the export uses; each is one Chemclaw3's `core.units.parse_unit` reads.
_UNITS = {"%", "area%", "% w/w"}
_MEASUREMENT_FIELDS = {
    "result_id",
    "sample_id",
    "lot",
    "method",
    "analyte",
    "value",
    "unit",
    "acquired_at",
}


def _entries_are_well_formed(exports: list[dict]) -> None:
    ids = [export["id"] for export in exports]
    assert len(ids) == len(set(ids)), (
        "two files claim one entry id; Chemclaw3 refuses both"
    )
    for export in exports:
        datetime.fromisoformat(export["timestamp"])
        assert isinstance(export["records"], list) and export["records"]


def test_every_lims_row_carries_what_the_measurement_kind_requires() -> None:
    exports = lims_exports()
    _entries_are_well_formed(exports)
    rows = [row for export in exports for row in export["records"]]
    result_ids = [row["result_id"] for row in rows]
    assert len(result_ids) == len(set(result_ids)), "a result id must name one result"
    for row in rows:
        assert _MEASUREMENT_FIELDS <= set(row), row
        assert row["unit"] in _UNITS
        assert row.get("uncertainty", 0) >= 0
        assert "source" not in row, (
            "Chemclaw3 stamps the source; an export must not claim one"
        )


def test_the_stability_series_rises_by_the_stated_amount() -> None:
    pulls = sorted(
        (row["study_months"], row["value"])
        for export in lims_exports()
        for row in export["records"]
        if "study_months" in row
    )
    assert [months for months, _ in pulls] == [0, 3, 6, 9, 12]
    rises = {
        round((later - earlier) / (m2 - m1), 6)
        for (m1, earlier), (m2, later) in pairwise(pulls)
    }
    assert rises == {IMPURITY_RISE_PER_MONTH}


def _labels_1536() -> set[str]:
    def row_label(row: int) -> str:
        return (
            chr(ord("A") + row)
            if row < 26
            else chr(ord("A") + row // 26 - 1) + chr(ord("A") + row % 26)
        )

    return {f"{row_label(r)}{c + 1}" for r in range(32) for c in range(48)}


@pytest.mark.parametrize(
    ("plate_id", "csv_name"),
    [
        ("SANTANILLA-AMIDATION", "santanilla_amidation_screen.csv"),
        ("SANTANILLA-SULFONAMIDATION", "santanilla_sulfonamidation_screen.csv"),
    ],
)
def test_each_plate_holds_its_real_screen_at_real_positions(
    plate_id: str, csv_name: str
) -> None:
    exports = {export["id"]: export for export in hte_plate_exports()}
    _entries_are_well_formed(list(exports.values()))
    (plate,) = exports[plate_id]["records"]
    assert plate["plate_format"] == 1536
    labels = [well["well"] for well in plate["wells"]]
    assert len(labels) == len(set(labels)) == 96, "each well once"
    assert set(labels) <= _labels_1536()
    with open(_REAL_DATA / csv_name, newline="", encoding="utf-8") as handle:
        published = {
            row["plate_position"]: float(row["yield_percent"])
            for row in csv.DictReader(handle)
        }
    stated = {
        well["well"]: well["reaction"]["products"][0]["yield_percent"]
        for well in plate["wells"]
    }
    assert stated == published, "a well's yield is the published one, never adjusted"
    for well in plate["wells"]:
        roles = [item["role"] for item in well["reaction"]["reactants"]]
        assert roles == ["reactant", "reactant", "catalyst", "reagent"]
        assert set(well["conditions"]) == {"precatalyst", "base"}


def test_the_seed_writes_both_drops_where_chemclaw3_reads_them(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "record_export_dir", tmp_path)
    (tmp_path / LIMS_SUBDIR).mkdir()
    (tmp_path / LIMS_SUBDIR / "stale.json").write_text("{}", "utf-8")
    counts = seed_records()
    assert counts == {"lims": len(lims_exports()), "hte": len(hte_plate_exports())}
    lims_files = sorted(p.stem for p in (tmp_path / LIMS_SUBDIR).glob("*.json"))
    assert "stale" not in lims_files, "a re-seed replaces the previous drop"
    assert lims_files == sorted(export["id"] for export in lims_exports())
    plate = json.loads(
        (tmp_path / HTE_SUBDIR / "SANTANILLA-AMIDATION.json").read_text("utf-8")
    )
    assert plate == next(
        e for e in hte_plate_exports() if e["id"] == "SANTANILLA-AMIDATION"
    )
    assert seed_records() == counts, "seeding twice is idempotent"


def test_the_app_seeds_both_drops_on_startup(client) -> None:
    root = settings.record_export_dir
    assert sorted(p.name for p in (root / LIMS_SUBDIR).glob("*.json"))
    assert sorted(p.name for p in (root / HTE_SUBDIR).glob("*.json"))
