"""Curated ELN fixture data: real named organic reactions, real SMILES.

Two independent representations of (mostly) the same chemistry, shaped exactly to what
Chemclaw3's two adapters expect (`eln/json_adapter.py`, `eln/ord_adapter.py`):

  - `uspto_style_records()` — free-text-heavy exports in the shape `JsonExportAdapter` reads:
    structured reactant/product SMILES, and a patent-style prose procedure most records lean on
    for temperature/time (regex-recovered) and step segmentation, the way real USPTO-derived
    reaction-extraction corpora look.
  - `ord_style_records()` — structured Open Reaction Database `Reaction` JSON in the shape
    `OrdJsonAdapter` reads: component-linked `inputs` (with addition order/time), `conditions`,
    and a `workups[]` sequence.

Not literal downloads (this mock stays fully offline per design) — every reaction is a real,
named transformation with a real SMILES, so the content exercises both adapters' structured and
free-text code paths (unit conversions, role mapping, step classification, regex temperature/time
recovery, impurities, an explicit failure record) against realistic chemistry rather than
placeholder data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

_BASE_TIME = datetime(2024, 1, 8, 9, 0, tzinfo=UTC)

# One real named reaction per archetype: reactants/reagents (with role), the product, a coarse
# reaction family label, and enough detail to render both a patent-style procedure and an ORD
# component-linked step sequence.
_ARCHETYPES: list[dict[str, Any]] = [
    {
        "key": "suzuki-biphenyl",
        "name": "Suzuki-Miyaura coupling to 4-methoxybiphenyl",
        "reactants": [
            ("COc1ccc(Br)cc1", "reactant", 935.0, 5.0),
            ("OB(O)c1ccccc1", "reactant", 671.0, 5.5),
            ("O=C([O-])[O-].[K+].[K+]", "reagent", 1382.0, 10.0),
            ("CC(C)(C)P(c1ccccc1)c1ccccc1", "catalyst", 30.0, 0.1),
        ],
        "product": "COc1ccc(-c2ccccc2)cc1",
        "temperature_c": 82.0,
        "time_h": 4.0,
        "yield_percent": 91.0,
        "purity_percent": 98.2,
        "solvent": "1,4-dioxane/water (4:1)",
    },
    {
        "key": "amide-coupling",
        "name": "EDC/HOBt amide coupling to N-phenylbenzamide",
        "reactants": [
            ("O=C(O)c1ccccc1", "reactant", 610.0, 5.0),
            ("Nc1ccccc1", "reactant", 466.0, 5.0),
            ("CCN=C=NCCCN(C)C", "reagent", 1053.0, 5.5),
            ("On1nnc2ccccc21", "reagent", 743.0, 5.5),
        ],
        "product": "O=C(Nc1ccccc1)c1ccccc1",
        "temperature_c": 22.0,
        "time_h": 16.0,
        "yield_percent": 84.0,
        "purity_percent": 97.0,
        "solvent": "dichloromethane",
    },
    {
        "key": "reductive-amination",
        "name": "Reductive amination to N-methylbenzylamine",
        "reactants": [
            ("O=Cc1ccccc1", "reactant", 530.0, 5.0),
            ("CN", "reactant", 8.0, 5.5),
            ("CC(=O)O[BH-](OC(C)=O)OC(C)=O.[Na+]", "reagent", 1590.0, 7.5),
        ],
        "product": "CNCc1ccccc1",
        "temperature_c": 0.0,
        "time_h": 3.0,
        "yield_percent": 78.0,
        "purity_percent": 95.5,
        "solvent": "1,2-dichloroethane",
    },
    {
        "key": "fischer-esterification",
        "name": "Fischer esterification to ethyl benzoate",
        "reactants": [
            ("O=C(O)c1ccccc1", "reactant", 1221.0, 10.0),
            ("CCO", "reactant", 4600.0, 100.0),
            ("OS(=O)(=O)O", "catalyst", 49.0, 0.5),
        ],
        "product": "CCOC(=O)c1ccccc1",
        "temperature_c": 78.0,
        "time_h": 6.0,
        "yield_percent": 88.0,
        "purity_percent": 99.0,
        "solvent": "ethanol (excess, also reactant)",
    },
    {
        "key": "grignard-benzhydrol",
        "name": "Grignard addition to benzhydrol",
        "reactants": [
            ("Brc1ccccc1", "reactant", 785.0, 5.0),
            ("[Mg]", "reagent", 122.0, 5.0),
            ("O=Cc1ccccc1", "reactant", 530.0, 5.0),
        ],
        "product": "OC(c1ccccc1)c1ccccc1",
        "temperature_c": 35.0,
        "time_h": 2.0,
        "yield_percent": 73.0,
        "purity_percent": 96.0,
        "solvent": "anhydrous THF",
    },
    {
        "key": "friedel-crafts-acylation",
        "name": "Friedel-Crafts acylation to acetophenone",
        "reactants": [
            ("c1ccccc1", "reactant", 3900.0, 50.0),
            ("CC(Cl)=O", "reactant", 785.0, 10.0),
            ("Cl[Al](Cl)Cl", "catalyst", 1467.0, 11.0),
        ],
        "product": "CC(=O)c1ccccc1",
        "temperature_c": 5.0,
        "time_h": 1.5,
        "yield_percent": 80.0,
        "purity_percent": 97.8,
        "solvent": "dichloromethane",
    },
    {
        "key": "wittig-styrene",
        "name": "Wittig olefination to styrene",
        "reactants": [
            ("O=Cc1ccccc1", "reactant", 530.0, 5.0),
            ("[CH2-]P(c1ccccc1)(c1ccccc1)c1ccccc1", "reagent", 1750.0, 5.2),
        ],
        "product": "C=Cc1ccccc1",
        "temperature_c": 25.0,
        "time_h": 12.0,
        "yield_percent": 69.0,
        "purity_percent": 94.0,
        "solvent": "anhydrous THF",
    },
    {
        "key": "snar-piperidine",
        "name": "SNAr amination to 1-(4-nitrophenyl)piperidine",
        "reactants": [
            ("O=[N+]([O-])c1ccc(F)cc1", "reactant", 705.0, 5.0),
            ("C1CCNCC1", "reactant", 468.0, 5.5),
            ("O=C([O-])[O-].[K+].[K+]", "reagent", 1382.0, 10.0),
        ],
        "product": "O=[N+]([O-])c1ccc(N2CCCCC2)cc1",
        "temperature_c": 90.0,
        "time_h": 8.0,
        "yield_percent": 92.0,
        "purity_percent": 98.5,
        "solvent": "DMSO",
    },
    {
        "key": "buchwald-hartwig",
        "name": "Buchwald-Hartwig amination to 4-(p-tolyl)morpholine",
        "reactants": [
            ("Cc1ccc(Br)cc1", "reactant", 855.0, 5.0),
            ("C1COCCN1", "reactant", 479.0, 5.5),
            ("O=C([O-])[O-].[Cs+].[Cs+]", "reagent", 2280.0, 7.0),
            ("CC(C)c1cc(C(C)C)c(-c2ccccc2P(C(C)(C)C)C(C)(C)C)c(C(C)C)c1", "catalyst", 48.0, 0.1),
        ],
        "product": "Cc1ccc(N2CCOCC2)cc1",
        "temperature_c": 100.0,
        "time_h": 14.0,
        "yield_percent": 87.0,
        "purity_percent": 97.5,
        "solvent": "toluene",
    },
    {
        "key": "sonogashira",
        "name": "Sonogashira coupling to diphenylacetylene",
        "reactants": [
            ("Ic1ccccc1", "reactant", 1020.0, 5.0),
            ("C#Cc1ccccc1", "reactant", 561.0, 5.5),
            ("[Cu]I", "catalyst", 19.0, 0.1),
        ],
        "product": "c1ccc(C#Cc2ccccc2)cc1",
        "temperature_c": 60.0,
        "time_h": 3.0,
        "yield_percent": 85.0,
        "purity_percent": 96.5,
        "solvent": "triethylamine/THF",
    },
    {
        "key": "epoxide-opening",
        "name": "Azide epoxide opening to 2-azido-1-phenylethanol",
        "reactants": [
            ("c1ccc(C2CO2)cc1", "reactant", 601.0, 5.0),
            ("[N-]=[N+]=[N-].[Na+]", "reactant", 358.0, 5.5),
            ("[NH4+].[Cl-]", "reagent", 267.0, 5.0),
        ],
        "product": "OC(CN=[N+]=[N-])c1ccccc1",
        "temperature_c": 65.0,
        "time_h": 5.0,
        "yield_percent": 76.0,
        "purity_percent": 95.0,
        "solvent": "ethanol/water (9:1)",
    },
    {
        "key": "boc-deprotection",
        "name": "Boc deprotection of tert-butyl 4-aminopiperidine-1-carboxylate",
        "reactants": [
            ("CC(C)(C)OC(=O)N1CCC(N)CC1", "reactant", 1071.0, 5.0),
            ("OC(=O)C(F)(F)F", "reagent", 5700.0, 50.0),
        ],
        "product": "NC1CCNCC1",
        "temperature_c": 22.0,
        "time_h": 1.0,
        "yield_percent": 95.0,
        "purity_percent": 99.5,
        "solvent": "dichloromethane",
    },
]

_OPERATORS = ["J. Alvarez", "M. Chen", "S. Patel", "R. Novak", "T. Adeyemi", "K. Fischer"]
_PROJECTS = ["PROJ-ALPHA", "PROJ-BETA", "PROJ-GAMMA", None]


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------------------
# USPTO-style free-text records (JsonExportAdapter shape)
# --------------------------------------------------------------------------------------


def _uspto_procedure(archetype: dict[str, Any], *, structured_conditions: bool) -> str:
    reactant_names = ", ".join(f"`{smi}`" for smi, *_ in archetype["reactants"][:2])
    temp = archetype["temperature_c"]
    time_h = archetype["time_h"]
    condition_clause = "" if structured_conditions else f" at {temp:.0f} °C for {time_h:.1f} h"
    return (
        f"1. A round-bottom flask was charged with {reactant_names} in "
        f"{archetype['solvent']}.\n"
        f"2. The mixture was stirred{condition_clause} under nitrogen.\n"
        f"3. The reaction was cooled to room temperature and quenched with saturated "
        f"aqueous NH4Cl.\n"
        f"4. The organic layer was washed with brine, dried over Na2SO4, and concentrated "
        f"under reduced pressure.\n"
        f"5. The crude product was purified by recrystallization to give the title "
        f"compound `{archetype['product']}`."
    )


def uspto_style_records() -> list[dict[str, Any]]:
    """Return (entry_id, payload) pairs shaped exactly for `JsonExportAdapter`."""
    records: list[dict[str, Any]] = []
    for i, arche in enumerate(_ARCHETYPES):
        for variant in range(2):
            idx = i * 2 + variant
            entry_id = f"uspto-{arche['key']}-{variant + 1}"
            timestamp = _BASE_TIME + timedelta(hours=idx * 7)
            operator = _OPERATORS[idx % len(_OPERATORS)]
            project = _PROJECTS[idx % len(_PROJECTS)]
            structured = variant == 1  # alternate: regex-recovered vs. structured conditions
            yield_pct = arche["yield_percent"] + (variant * 3 - 1.5)
            purity_pct = arche["purity_percent"] - variant * 0.4
            reactants = [
                {
                    "smiles": smi,
                    "role": role,
                    "mass_mg": mass_mg,
                    "amount_mmol": amount_mmol,
                }
                for smi, role, mass_mg, amount_mmol in arche["reactants"]
            ]
            product_entry: dict[str, Any] = {
                "smiles": arche["product"],
                "yield_percent": round(yield_pct, 1),
                "purity_percent": round(purity_pct, 1),
            }
            payload: dict[str, Any] = {
                "id": entry_id,
                "timestamp": _iso(timestamp),
                "reactants": reactants,
                "products": [product_entry],
                "procedure": _uspto_procedure(arche, structured_conditions=structured),
                "operator": operator,
            }
            if project:
                payload["project"] = project
            if structured:
                payload["temperature_c"] = arche["temperature_c"]
                payload["time_h"] = arche["time_h"]
            records.append(payload)

    # One explicit impurity profile (exercises `_impurities`).
    records[0]["products"][0]["impurities"] = [
        {"name": "des-methoxy biphenyl", "smiles": "c1ccc(-c2ccccc2)cc1", "area_percent": 1.4},
        {"name": None, "smiles": "COc1ccc(Br)cc1", "area_percent": 0.3},
    ]

    # One explicit failure record (exercises `outcome_class` / `failure_reason`).
    failed = dict(records[-1])
    failed["id"] = "uspto-boc-deprotection-failed"
    failed["timestamp"] = _iso(_BASE_TIME + timedelta(hours=200))
    failed["outcome"] = "failure"
    failed["failure_reason"] = "TFA cleavage stalled; starting material recovered by TLC/LCMS."
    failed["products"] = [{"smiles": _ARCHETYPES[-1]["product"], "yield_percent": 4.0}]
    records.append(failed)

    return records


# --------------------------------------------------------------------------------------
# ORD-style structured records (OrdJsonAdapter shape)
# --------------------------------------------------------------------------------------

_ROLE_TO_ORD = {
    "reactant": "REACTANT",
    "reagent": "REAGENT",
    "solvent": "SOLVENT",
    "catalyst": "CATALYST",
}


def _ord_component(smiles: str, role: str, mass_mg: float, amount_mmol: float) -> dict[str, Any]:
    return {
        "identifiers": [{"type": "SMILES", "value": smiles}],
        "reactionRole": _ROLE_TO_ORD[role],
        "amount": {
            "mass": {"value": mass_mg, "units": "MILLIGRAM"},
            "moles": {"value": amount_mmol, "units": "MILLIMOLE"},
        },
    }


def ord_style_records() -> list[dict[str, Any]]:
    """Return payloads shaped exactly for `OrdJsonAdapter` (component-linked, structured)."""
    records: list[dict[str, Any]] = []
    for i, arche in enumerate(_ARCHETYPES):
        for variant in range(2):
            idx = i * 2 + variant
            entry_id = f"ord-{arche['key']}-{variant + 1}"
            timestamp = _BASE_TIME + timedelta(hours=idx * 7 + 3)
            person = _OPERATORS[(idx + 1) % len(_OPERATORS)]
            yield_pct = arche["yield_percent"] + (variant * 2 - 1.0)
            purity_pct = arche["purity_percent"] - variant * 0.3

            inputs: dict[str, Any] = {}
            for j, (smi, role, mass_mg, amount_mmol) in enumerate(arche["reactants"]):
                inputs[f"input_{j + 1}"] = {
                    "components": [_ord_component(smi, role, mass_mg, amount_mmol)],
                    "additionOrder": j + 1,
                    "additionTime": {"value": 5.0 * j, "units": "MINUTE"},
                }

            payload: dict[str, Any] = {
                "reactionId": entry_id,
                "inputs": inputs,
                "conditions": {
                    "temperature": {
                        "setpoint": {"value": arche["temperature_c"], "units": "CELSIUS"}
                    }
                },
                "outcomes": [
                    {
                        "products": [
                            {
                                "identifiers": [{"type": "SMILES", "value": arche["product"]}],
                                "measurements": [
                                    {"type": "YIELD", "percentage": {"value": round(yield_pct, 1)}},
                                    {
                                        "type": "PURITY",
                                        "percentage": {"value": round(purity_pct, 1)},
                                    },
                                ],
                            }
                        ]
                    }
                ],
                "workups": [
                    {
                        "type": "WASH",
                        "details": f"Washed with brine ({arche['solvent']} extraction)",
                        "input": {
                            "components": [
                                {
                                    "identifiers": [{"type": "SMILES", "value": "O"}],
                                    "reactionRole": "SOLVENT",
                                }
                            ]
                        },
                        "duration": {"value": 10.0, "units": "MINUTE"},
                    },
                    {
                        "type": "FILTRATION",
                        "details": "Filtered through Celite and concentrated in vacuo",
                    },
                ],
                "notes": {
                    "procedureDetails": (
                        f"{arche['name']}: charged sequentially per addition order, held at "
                        f"{arche['temperature_c']:.0f} °C for {arche['time_h']:.1f} h, then "
                        "worked up and purified by recrystallization."
                    )
                },
                "provenance": {
                    "recordCreated": {
                        "time": {"value": _iso(timestamp)},
                        "person": {"name": person},
                    }
                },
            }
            records.append(payload)
    return records
