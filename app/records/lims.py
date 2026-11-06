"""A LIMS export: analytical results per sample, in Chemclaw3's record-drop shape.

One file per sample, `{"id", "timestamp", "records": [...]}`, each record one analyte measured by
one method — the rows Chemclaw3's `measurement` kind validates (`ingest/records/kinds/
measurement.py`). Curated and deterministic, not real data: three release lots with assay, largest
impurity and water results, and a stability study on one lot (0, 3, 6, 9, 12 months) whose
impurity rises linearly so a trend fit has a known answer. Every unit is one `core.units` reads.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

_BASE_TIME = datetime(2026, 1, 12, 8, 0, tzinfo=UTC)

# (lot, assay %, largest impurity %, water content %w/w): release results, one sample per lot.
_RELEASE = (
    ("LOT-2026-A", 99.4, 0.06, 0.11),
    ("LOT-2026-B", 98.7, 0.12, 0.18),
    ("LOT-2026-C", 99.1, 0.09, 0.42),
)

# The stability lot, its pulls in months, and the impurity at time zero and its rise per month.
_STABILITY_LOT = "LOT-2026-A"
_STABILITY_MONTHS = (0, 3, 6, 9, 12)
_IMPURITY_AT_ZERO = 0.06
IMPURITY_RISE_PER_MONTH = 0.004

_METHODS = {
    "assay": ("HPLC-ASSAY-01", "HPLC-07", "%", 0.3),
    "largest impurity": ("HPLC-IMP-02", "HPLC-07", "area%", 0.01),
    "water content": ("KF-01", "KF-02", "% w/w", None),
}


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _result(
    sample_id: str,
    lot: str,
    analyte: str,
    value: float,
    acquired_at: datetime,
    *,
    study_months: float | None = None,
) -> dict[str, Any]:
    method, instrument, unit, uncertainty = _METHODS[analyte]
    row: dict[str, Any] = {
        "result_id": f"{sample_id}-{method}",
        "sample_id": sample_id,
        "lot": lot,
        "method": method,
        "analyte": analyte,
        "value": round(value, 4),
        "unit": unit,
        "instrument": instrument,
        "acquired_at": _iso(acquired_at),
        "raw_ref": f"lims://samples/{sample_id}/{method}",
    }
    if uncertainty is not None:
        row["uncertainty"] = uncertainty
    if study_months is not None:
        row["study_months"] = study_months
    return row


def lims_exports() -> list[dict[str, Any]]:
    """Every sample's export file, oldest first: the release lots, then the stability pulls."""
    exports: list[dict[str, Any]] = []
    for index, (lot, assay, impurity, water) in enumerate(_RELEASE):
        acquired = _BASE_TIME + timedelta(days=index)
        sample_id = f"S-{lot}-REL"
        exports.append(
            {
                "id": sample_id,
                "timestamp": _iso(acquired + timedelta(hours=2)),
                "records": [
                    _result(sample_id, lot, "assay", assay, acquired),
                    _result(sample_id, lot, "largest impurity", impurity, acquired),
                    _result(sample_id, lot, "water content", water, acquired),
                ],
            }
        )
    for months in _STABILITY_MONTHS:
        acquired = _BASE_TIME + timedelta(days=30 * months + 1)
        sample_id = f"S-{_STABILITY_LOT}-STAB-M{months:02d}"
        impurity = _IMPURITY_AT_ZERO + IMPURITY_RISE_PER_MONTH * months
        exports.append(
            {
                "id": sample_id,
                "timestamp": _iso(acquired + timedelta(hours=2)),
                "records": [
                    _result(
                        sample_id,
                        _STABILITY_LOT,
                        "largest impurity",
                        impurity,
                        acquired,
                        study_months=months,
                    )
                ],
            }
        )
    return exports
