"""Structured ORD/OrdJsonAdapter-shape records built from REAL, published HTE datasets.

Every reaction, reagent, and yield value here is real measured data pulled from public HTE
datasets and expanded into Chemclaw3's `OrdJsonAdapter` shape (component-linked `inputs`,
`conditions`, `outcomes[].products[].measurements`) — nothing in this module is synthesized
chemistry. The compact raw factor tables live as committed CSVs in `app/eln/real_data/`
(fetched once from their public sources; see below and README.md for exact provenance) and are
expanded here at seed time with no network access needed at runtime.

Sources:
  - Buchwald-Hartwig amination (`bh-amination-plate-{p2et,mtbd,btmg}`): Ahneman, Estrada, Lin,
    Dreher, Doyle. "Predicting reaction performance in C-N cross-coupling using machine
    learning." Science 2018, 360, 186-190. DOI 10.1126/science.aar5169. 3,955 real reactions
    (aryl halide + 4-methylaniline, Pd/ligand, base, isoxazole additive), which the original HTE
    campaign ran as 3 physical plates -- one base per plate (P2Et/MTBD/BTMG) -- reconstructed
    here from the base column. This is Buchwald-Hartwig AMINATION, not amidation; no comparable
    public amidation HTE benchmark of this scale was found (see README).
  - Suzuki-Miyaura flow HTE (`suzuki-miyaura-flow-hte`): Perera et al. "A platform for automated
    nanomole-scale reaction screening and micromole-scale synthesis in flow." Science 2018, 359,
    429-434. DOI 10.1126/science.aap9112. 5,760 real reactions. The non-quinoline coupling
    partner is only identified by the paper's own shorthand codes (2a-2d) with no SMILES
    published in the source spreadsheet, so it is carried as a real `NAME` identifier rather than
    a guessed structure.
  - Buchwald-Hartwig-type amidation / sulfonamidation (`santanilla-amidation-screen`,
    `santanilla-sulfonamidation-screen`): Santanilla et al. "Nanomole-scale high-throughput
    chemistry for the synthesis of complex molecules." Science 2015, 347, 49-53. DOI
    10.1126/science.1259203, Experiment 2 (1536-well nanomole-scale screen), the "amide S4" /
    "sulfonamide S5" nucleophile subsets specifically: real 3-bromopyridine + benzamide /
    benzenesulfonamide Pd-catalyzed N-arylation across 16 real precatalysts x 6 real bases (96
    real reactions each). This is genuine Buchwald-Hartwig amidation chemistry.
  - Deoxyfluorination screen (`nielsen-deoxyfluorination-screen`): Nielsen et al. "Deoxy-
    fluorination with Sulfonyl Fluorides: Navigating Reaction Space with Machine Learning."
    J. Am. Chem. Soc. 2018, 140, 5004-5008. DOI 10.1021/jacs.8b01523. 80 real reactions (Figure
    1 / Table 1 of the paper).
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent / "real_data"

_ROLE = {
    "reactant": "REACTANT",
    "reagent": "REAGENT",
    "catalyst": "CATALYST",
    "solvent": "SOLVENT",
}


def _read_csv(name: str) -> list[dict[str, str]]:
    with open(_DATA_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _component(
    smiles: str | None, role: str, *, name: str | None = None
) -> dict[str, Any]:
    identifiers: list[dict[str, str]] = []
    if smiles:
        identifiers.append({"type": "SMILES", "value": smiles})
    if name:
        identifiers.append({"type": "NAME", "value": name})
    return {"identifiers": identifiers, "reactionRole": _ROLE[role]}


def _ord_record(
    *,
    reaction_id: str,
    dataset_id: str,
    reaction_class: str,
    inputs: list[tuple[str, dict[str, Any]]],
    product_smiles: str | None,
    product_name: str | None,
    yield_percent: float,
    timestamp: datetime,
    doi: str,
    notes: str,
    temperature_c: float | None = None,
    reaction_time_h: float | None = None,
    well: str | None = None,
) -> dict[str, Any]:
    inputs_dict: dict[str, Any] = {}
    for order, (name, component) in enumerate(inputs, start=1):
        inputs_dict[name] = {"components": [component], "additionOrder": order}

    conditions: dict[str, Any] = {}
    if temperature_c is not None:
        conditions["temperature"] = {"setpoint": {"value": temperature_c, "units": "CELSIUS"}}

    outcome: dict[str, Any] = {
        "products": [
            {
                "identifiers": [
                    i
                    for i in (
                        {"type": "SMILES", "value": product_smiles} if product_smiles else None,
                        {"type": "NAME", "value": product_name} if product_name else None,
                    )
                    if i is not None
                ],
                "measurements": [
                    {"type": "YIELD", "percentage": {"value": round(yield_percent, 2)}}
                ],
            }
        ]
    }
    if reaction_time_h is not None:
        outcome["reactionTime"] = {"value": reaction_time_h, "units": "HOUR"}

    record: dict[str, Any] = {
        "reactionId": reaction_id,
        "datasetId": dataset_id,
        "reactionClass": reaction_class,
        "inputs": inputs_dict,
        "conditions": conditions,
        "outcomes": [outcome],
        "notes": {"procedureDetails": notes},
        "provenance": {
            "doi": doi,
            "recordCreated": {
                "time": {"value": _iso(timestamp)},
                "person": {"name": "Real HTE dataset import"},
            },
        },
    }
    if well:
        record["well"] = well
    return record


# --------------------------------------------------------------------------------------
# Buchwald-Hartwig amination -- Ahneman/Dreher/Doyle, Science 2018 (real, 3 real plates)
# --------------------------------------------------------------------------------------

_BH_DOI = "10.1126/science.aar5169"
_BH_AMINE_SMILES = "Cc1ccc(N)cc1"  # 4-methylaniline, the fixed real coupling partner
_BH_PLATE_DATASET_ID = {
    "P2Et": "bh-amination-plate-p2et",
    "MTBD": "bh-amination-plate-mtbd",
    "BTMG": "bh-amination-plate-btmg",
}
_BH_BASE_TIME = datetime(2023, 3, 1, 9, 0, tzinfo=UTC)


def bh_amination_hte_records() -> list[dict[str, Any]]:
    """3,955 real reactions from the Ahneman/Doyle Science 2018 HTE campaign.

    Split into 3 real physical screening plates (one per base), matching how the original
    campaign was actually run.
    """
    rows = _read_csv("bh_amination_hte.csv")
    records = []
    plate_counters: dict[str, int] = {}
    for row in rows:
        plate = row["plate"]
        dataset_id = _BH_PLATE_DATASET_ID[plate]
        idx = plate_counters.get(plate, 0)
        plate_counters[plate] = idx + 1
        timestamp = _BH_BASE_TIME + timedelta(minutes=idx * 3)
        aryl_halide = row["aryl_halide_smiles"]
        records.append(
            _ord_record(
                reaction_id=f"bh-amination-{plate.lower()}-{idx:04d}",
                dataset_id=dataset_id,
                reaction_class="buchwald-hartwig-amination",
                inputs=[
                    ("aryl halide", _component(aryl_halide, "reactant")),
                    ("4-methylaniline", _component(_BH_AMINE_SMILES, "reactant")),
                    ("ligand", _component(row["ligand_smiles"], "catalyst")),
                    ("base", _component(row["base_smiles"], "reagent")),
                    (
                        "isoxazole additive",
                        _component(row["additive_smiles"], "reagent"),
                    ),
                ],
                product_smiles=row["product_smiles"],
                product_name=None,
                yield_percent=float(row["yield_percent"]),
                timestamp=timestamp,
                doi=_BH_DOI,
                notes=(
                    "Real HTE well from Ahneman et al., Science 2018, 360, 186-190 "
                    f"(plate {plate}): Pd/ligand-catalyzed C-N coupling of the aryl halide with "
                    "4-methylaniline, screened against an isoxazole functional-group-tolerance "
                    "additive. UPLC yield relative to an internal standard."
                ),
            )
        )
    return records


# --------------------------------------------------------------------------------------
# Suzuki-Miyaura flow HTE -- Perera et al., Science 2018 (real, 5,760 reactions)
# --------------------------------------------------------------------------------------

_SUZUKI_DOI = "10.1126/science.aap9112"
_SUZUKI_BASE_TIME = datetime(2023, 4, 1, 9, 0, tzinfo=UTC)


def suzuki_miyaura_flow_hte_records() -> list[dict[str, Any]]:
    """5,760 real reactions from the Perera et al. Science 2018 flow-chemistry HTE platform.

    The non-quinoline coupling partner (paper shorthand `2a`-`2d`) has no published SMILES in
    the source spreadsheet, so it is carried as a real `NAME` identifier rather than a guessed
    structure -- see module docstring.
    """
    rows = _read_csv("suzuki_miyaura_flow_hte.csv")
    records = []
    for idx, row in enumerate(rows):
        timestamp = _SUZUKI_BASE_TIME + timedelta(minutes=idx * 2)
        inputs = [
            ("quinoline coupling partner", _component(row["r1_smiles"], "reactant")),
            (
                "second coupling partner",
                _component(None, "reactant", name=row["r2_name"]),
            ),
            ("catalyst", _component(row["catalyst_smiles"], "catalyst")),
        ]
        if row["ligand_smiles"]:
            inputs.append(("ligand", _component(row["ligand_smiles"], "catalyst", name=row["ligand_name"])))
        if row["base_smiles"]:
            inputs.append(("base", _component(row["base_smiles"], "reagent", name=row["base_name"])))
        records.append(
            _ord_record(
                reaction_id=f"suzuki-flow-hte-{int(row['reaction_no']):05d}",
                dataset_id="suzuki-miyaura-flow-hte",
                reaction_class="suzuki-miyaura",
                inputs=inputs,
                product_smiles=None,
                product_name=f"Suzuki-Miyaura coupling product of {row['r1_name']} with {row['r2_name']}",
                yield_percent=float(row["yield_pct_uv"]),
                timestamp=timestamp,
                doi=_SUZUKI_DOI,
                notes=(
                    "Real reaction from Perera et al., Science 2018, 359, 429-434: automated "
                    f"nanomole-scale flow screening of {row['r1_name']} with {row['r2_name']} "
                    f"in {row['solvent_name']}. UPLC-UV area-percent yield."
                ),
            )
        )
    return records


# --------------------------------------------------------------------------------------
# Buchwald-Hartwig-type amidation / sulfonamidation -- Santanilla et al., Science 2015
# --------------------------------------------------------------------------------------

_SANTANILLA_DOI = "10.1126/science.1259203"
_SANTANILLA_BASE_TIME = datetime(2023, 5, 1, 9, 0, tzinfo=UTC)
_SANTANILLA_QUOTED_PROCEDURE = (
    "A 1536-well plate experiment examining the reactivity of 3-bromopyridine 22 with 16 "
    "different classes of nucleophiles under 96 Pd cross-coupling reaction conditions was run "
    "at 100 nanomolar scale by dosing from a 384-well plate containing stock solutions of the "
    "starting materials and reagents into a 1536-well plate by Mosquito. Stock solutions of "
    "each of the reaction components were prepared as follows: Pd-precatalysts (0.04 M in "
    "DMSO), aryl halide (0.4 M in DMSO), nucleophiles (0.6 M in DMSO), and base (0.8 M in "
    "DMSO). The plate was allowed to sit at room temperature for 22 hours, then quenched and "
    "analyzed by UPLC (real, quoted procedure from the paper's SI, DOI "
    "10.1126/science.1259203, Experiment 2)."
)


def _santanilla_screen_records(
    filename: str, dataset_id: str, reaction_class: str, nucleophile_label: str
) -> list[dict[str, Any]]:
    rows = _read_csv(filename)
    records = []
    for idx, row in enumerate(rows):
        timestamp = _SANTANILLA_BASE_TIME + timedelta(minutes=idx * 5)
        records.append(
            _ord_record(
                reaction_id=f"{dataset_id}-{idx:04d}",
                dataset_id=dataset_id,
                reaction_class=reaction_class,
                inputs=[
                    ("aryl halide", _component(row["aryl_halide_smiles"], "reactant")),
                    (
                        "nucleophile",
                        _component(row["nucleophile_smiles"], "reactant", name=nucleophile_label),
                    ),
                    (
                        "precatalyst",
                        _component(row["catalyst_smiles"], "catalyst", name=row["catalyst_name"]),
                    ),
                    ("base", _component(row["base_smiles"], "reagent", name=row["base_name"])),
                ],
                product_smiles=row["product_smiles"],
                product_name=None,
                yield_percent=float(row["yield_percent"]),
                timestamp=timestamp,
                doi=_SANTANILLA_DOI,
                reaction_time_h=22.0,
                well=row["plate_position"],
                notes=_SANTANILLA_QUOTED_PROCEDURE,
            )
        )
    return records


def santanilla_amidation_hte_records() -> list[dict[str, Any]]:
    """96 real Buchwald-Hartwig amidation reactions (3-bromopyridine + benzamide)."""
    return _santanilla_screen_records(
        "santanilla_amidation_screen.csv",
        "santanilla-amidation-screen",
        "buchwald-hartwig-amidation",
        "amide S4 (benzamide)",
    )


def santanilla_sulfonamidation_hte_records() -> list[dict[str, Any]]:
    """96 real Buchwald-Hartwig-type sulfonamidation reactions (3-bromopyridine + benzenesulfonamide)."""
    return _santanilla_screen_records(
        "santanilla_sulfonamidation_screen.csv",
        "santanilla-sulfonamidation-screen",
        "buchwald-hartwig-sulfonamidation",
        "sulfonamide S5 (benzenesulfonamide)",
    )


# --------------------------------------------------------------------------------------
# Deoxyfluorination screen -- Nielsen et al., JACS 2018 (real, 80 reactions)
# --------------------------------------------------------------------------------------

_NIELSEN_DOI = "10.1021/jacs.8b01523"
_NIELSEN_BASE_TIME = datetime(2023, 6, 1, 9, 0, tzinfo=UTC)


def nielsen_deoxyfluorination_hte_records() -> list[dict[str, Any]]:
    """80 real reactions from Nielsen et al., JACS 2018 (Figure 1 / Table 1)."""
    rows = _read_csv("nielsen_deoxyfluorination.csv")
    records = []
    for idx, row in enumerate(rows):
        timestamp = _NIELSEN_BASE_TIME + timedelta(minutes=idx * 5)
        records.append(
            _ord_record(
                reaction_id=f"nielsen-deoxyfluorination-{idx:04d}",
                dataset_id="nielsen-deoxyfluorination-screen",
                reaction_class="deoxyfluorination",
                inputs=[
                    ("alcohol", _component(row["alcohol_smiles"], "reactant")),
                    ("sulfonyl fluoride", _component(row["sulfonyl_fluoride_smiles"], "reactant")),
                    ("base", _component(row["base_smiles"], "reagent")),
                ],
                product_smiles=row["product_smiles"],
                product_name=None,
                yield_percent=float(row["product_yield"]),
                timestamp=timestamp,
                doi=_NIELSEN_DOI,
                temperature_c=23.0,
                reaction_time_h=48.0,
                notes=(
                    "Real reaction from Nielsen et al., JACS 2018, 140, 5004-5008 (Figure 1 / "
                    "Table 1): deoxyfluorination of the alcohol with the sulfonyl fluoride, "
                    "ambient temperature, sealed 1 mL glass vial, 19F NMR yield vs. an internal "
                    "standard (1-fluoronaphthalene) after 48 h."
                ),
            )
        )
    return records


def all_real_hte_records(
    *, max_per_dataset: int | None = None
) -> dict[str, list[dict[str, Any]]]:
    """All real HTE datasets, keyed by datasetId, ready to be written to disk by seed.py.

    `max_per_dataset` truncates each dataset to its first N rows (deterministic, real data
    only reordered/dropped, never fabricated) -- used to keep the test suite fast without
    shrinking the real dataset used at actual runtime (see `MOCK_HTE_MAX_RECORDS_PER_DATASET`
    in app/config.py). `None`/unset keeps every real record.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in bh_amination_hte_records():
        grouped.setdefault(record["datasetId"], []).append(record)
    for record in suzuki_miyaura_flow_hte_records():
        grouped.setdefault(record["datasetId"], []).append(record)
    for record in santanilla_amidation_hte_records():
        grouped.setdefault(record["datasetId"], []).append(record)
    for record in santanilla_sulfonamidation_hte_records():
        grouped.setdefault(record["datasetId"], []).append(record)
    for record in nielsen_deoxyfluorination_hte_records():
        grouped.setdefault(record["datasetId"], []).append(record)
    if max_per_dataset is not None:
        grouped = {k: v[:max_per_dataset] for k, v in grouped.items()}
    return grouped
