"""Free-text (JsonExportAdapter-shape) ELN records built from REAL, cited published procedures.

Every entry here traces to a real paper (DOI cited in the `procedure` text and `project`
field) -- no invented chemistry, no templated prose. This corpus is intentionally small: bulk
real USPTO-patent procedure text lives behind hosts (figshare, the official Open Reaction
Database Hugging Face mirror, Zenodo, Kaggle, IBM Box) that this environment's network policy
blocks, and no GitHub-committed real corpus of that scale was found (see README.md for the
full account). Rather than pad the count with generated/templated text, this module stays
small and fully real.

Sources:
  - 3 procedures from Liu, R. Y. "Copper-Catalyzed Enantioselective Hydroamination of Alkenes."
    Org. Synth. 2018, 95, 80-96. DOI 10.15227/orgsyn.095.0080. Quantities, conditions, workup
    steps, and analytical data (NMR/IR/HRMS/yield/purity/ee) are taken directly from the real
    ORD example submission for this paper (`ord-schema` repo,
    `examples/submissions/3_Liu_Copper_OrgSyn`); masses for volume-dosed reagents/solvents are
    computed from the real dosed volume and the compound's standard literature density.
  - 4 representative wells from Santanilla et al. "Nanomole-scale high-throughput chemistry for
    the synthesis of complex molecules." Science 2015, 347, 49-53. DOI 10.1126/science.1259203,
    Experiment 2 -- the highest-yielding real well for 4 other nucleophile classes in that same
    1536-well screen (aniline/amination, boronate/Suzuki, alkyne/Sonogashira,
    alcohol/etherification), narrated using the paper's own real quoted general procedure text.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

_BASE_TIME = datetime(2023, 7, 1, 9, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _reactant(smiles: str, role: str, mass_mg: float, amount_mmol: float) -> dict[str, Any]:
    return {
        "smiles": smiles,
        "role": role,
        "mass_mg": round(mass_mg, 2),
        "amount_mmol": round(amount_mmol, 3),
    }


_LIU_PROJECT = "Org. Synth. 2018, 95, 80-96 (DOI 10.15227/orgsyn.095.0080)"


def _liu_records() -> list[dict[str, Any]]:
    records = []

    # Procedure 1: N,N-Dibenzyl-O-pivaloylhydroxylamine
    records.append(
        {
            "id": "liu-orgsyn-procedure-1",
            "timestamp": _iso(_BASE_TIME),
            "reactants": [
                _reactant("C1=CC=C(C=C1)CN(CC2=CC=CC=C2)O", "reactant", 21300, 99.87),
                _reactant("n1ccc(N(C)C)cc1", "reagent", 12800, 104.77),
                _reactant("C(Cl)Cl", "solvent", 331650, 3904.84),
                _reactant("CC(C)(C)C(=O)Cl", "reactant", 12668, 105.06),
            ],
            "products": [
                {
                    "smiles": "O=C(C(C)(C)C)ON(CC1=CC=CC=C1)CC2=CC=CC=C2",
                    "yield_percent": 93.5,
                    "purity_percent": 99.0,
                }
            ],
            "procedure": (
                "1. An oven-dried 500-mL single-necked round-bottom flask, sealed with a "
                "rubber septum and purged with nitrogen, was charged in order with "
                "N,N-dibenzylhydroxylamine (21.3 g, 99.9 mmol, limiting reagent), "
                "4-dimethylaminopyridine (12.8 g, 104.8 mmol), and dichloromethane (250 mL, "
                "dried by passage through neutral alumina and copper(II) oxide).\n"
                "2. The suspension was cooled in an ice bath, and pivaloyl chloride (12.9 mL, "
                "105.1 mmol) was added dropwise via syringe over 5 min.\n"
                "3. The mixture was allowed to warm to 23 degC and stirred for an additional 6 h "
                "at room temperature under a slight positive nitrogen pressure.\n"
                "4. The reaction was quenched with 50 mL saturated aqueous ammonium chloride and "
                "extracted with dichloromethane (3 x 50 mL); the combined organics were washed "
                "with 200 mL water and concentrated on a rotary evaporator (30 degC, 80 mmHg).\n"
                "5. The residue was purified by chromatography on neutral alumina (100 g, "
                "dichloromethane eluent) to give the title compound "
                "`O=C(C(C)(C)C)ON(CC1=CC=CC=C1)CC2=CC=CC=C2` (27.75 g, 93.5% yield, 99% purity "
                "by quantitative 1H NMR; 1H NMR (400 MHz, CDCl3): 0.92 (s, 9H), 4.06 (s, 4H), "
                "7.23-7.34 (m, 6H), 7.40 (d, J = 7.1 Hz, 4H); HRMS (ESI-TOF) calc'd 298.1802, "
                f"found 298.1794).\n\nSource: {_LIU_PROJECT}. Experimenter: Richard Y. Liu, MIT."
            ),
            "operator": "Richard Y. Liu",
            "project": _LIU_PROJECT,
            "temperature_c": 23.0,
            "time_h": 6.0,
        }
    )

    # Procedure 2: (R)-N,N-Dibenzyl-1-phenylpropan-1-amine
    records.append(
        {
            "id": "liu-orgsyn-procedure-2",
            "timestamp": _iso(_BASE_TIME + timedelta(hours=8)),
            "reactants": [
                _reactant(
                    "O=C(C(C)(C)C)ON(CC1=CC=CC=C1)CC2=CC=CC=C2", "reactant", 7550, 25.39
                ),
                _reactant("CC(=O)[O-].CC(=O)[O-].[Cu+2]", "catalyst", 38, 0.209),
                _reactant(
                    "CC(C)(C)C1=CC(=CC(=C1OC)C(C)(C)C)P(C2=C(C3=C(C=C2)OCO3)C4=C(C=CC5=C4OCO5)"
                    "P(C6=CC(=C(C(=C6)C(C)(C)C)OC)C(C)(C)C)C7=CC(=C(C(=C7)C(C)(C)C)OC)C(C)(C)C)"
                    "C8=CC(=C(C(=C8)C(C)(C)C)OC)C(C)(C)C",
                    "catalyst",
                    274,
                    0.232,
                ),
                _reactant("c3c(P(c1ccccc1)c2ccccc2)cccc3", "catalyst", 61, 0.233),
                _reactant("C/C=C/C1=CC=CC=C1", "reactant", 2500, 21.15),
                _reactant("C1CCOC1", "solvent", 18673, 258.97),
                _reactant("CO[Si](C)OC", "reagent", 4490, 42.69),
            ],
            "products": [
                {
                    "smiles": "CC[C@@H](N(CC1=CC=CC=C1)CC2=CC=CC=C2)C3=CC=CC=C3",
                    "yield_percent": 86.0,
                    "purity_percent": 99.0,
                }
            ],
            "procedure": (
                "1. An oven-dried 250-mL two-necked round-bottom flask, sealed with rubber "
                "septa under nitrogen, was charged with N,N-Dibenzyl-O-pivaloylhydroxylamine "
                "(7.55 g, 25.4 mmol, from Procedure 1), copper(II) acetate (38 mg, 0.21 mmol), "
                "(S)-DTBM-SEGPHOS (274 mg, 0.23 mmol), triphenylphosphine (61 mg, 0.23 mmol), "
                "trans-beta-methylstyrene (2.50 g, 21.2 mmol, limiting reagent), and THF (21 mL, "
                "dried, via syringe).\n"
                "2. dimethoxy(methyl)silane (4.49 g, 42.7 mmol) was added dropwise via syringe "
                "over 10 min with the flask in a 23 degC water bath; the mixture turned blue on "
                "addition, then orange by 10 min.\n"
                "3. The water bath was removed and the mixture stirred for an additional 12 h at "
                "room temperature.\n"
                "4. The reaction was quenched with 50 mL saturated aqueous sodium bicarbonate and "
                "extracted with ethyl acetate (3 x 50 mL); the combined organics were "
                "concentrated on a rotary evaporator (35 degC, 50 mmHg).\n"
                "5. The residue was purified by silica chromatography (hexanes, then 1% then 2% "
                "EtOAc/hexanes) to give the title compound "
                "`CC[C@@H](N(CC1=CC=CC=C1)CC2=CC=CC=C2)C3=CC=CC=C3` (5.72 g, 86% yield, 99% "
                "purity by quantitative 1H NMR, 99% ee by chiral HPLC (Chiralpak OD-H, 4% "
                "iPrOH/hexanes); [alpha]D = +108 (c = 1.0, CHCl3)).\n\n"
                f"Source: {_LIU_PROJECT}. Experimenter: Richard Y. Liu, MIT."
            ),
            "operator": "Richard Y. Liu",
            "project": _LIU_PROJECT,
            "time_h": 12.0,
        }
    )

    # Procedure 3: (R)-N,N-Dibenzyl-2,3,3-trimethylbutan-1-amine
    records.append(
        {
            "id": "liu-orgsyn-procedure-3",
            "timestamp": _iso(_BASE_TIME + timedelta(hours=16)),
            "reactants": [
                _reactant(
                    "O=C(C(C)(C)C)ON(CC1=CC=CC=C1)CC2=CC=CC=C2", "reactant", 9090, 30.57
                ),
                _reactant("CC(=O)[O-].CC(=O)[O-].[Cu+2]", "catalyst", 46, 0.253),
                _reactant(
                    "CC(C)(C)C1=CC(=CC(=C1OC)C(C)(C)C)P(C2=C(C3=C(C=C2)OCO3)C4=C(C=CC5=C4OCO5)"
                    "P(C6=CC(=C(C(=C6)C(C)(C)C)OC)C(C)(C)C)C7=CC(=C(C(=C7)C(C)(C)C)OC)C(C)(C)C)"
                    "C8=CC(=C(C(=C8)C(C)(C)C)OC)C(C)(C)C",
                    "catalyst",
                    330,
                    0.280,
                ),
                _reactant("c3c(P(c1ccccc1)c2ccccc2)cccc3", "catalyst", 74, 0.282),
                _reactant("CC(=C)C(C)(C)C", "reactant", 2500, 25.46),
                _reactant("C1CCOC1", "solvent", 22230, 308.29),
                _reactant("CO[Si](C)OC", "reagent", 5410, 51.43),
            ],
            "products": [
                {
                    "smiles": "C[C@@H](CN(CC1=CC=CC=C1)CC2=CC=CC=C2)C(C)(C)C",
                    "yield_percent": 87.0,
                    "purity_percent": 97.0,
                }
            ],
            "procedure": (
                "1. An oven-dried 250-mL two-necked round-bottom flask, sealed with rubber "
                "septa under nitrogen, was charged with N,N-Dibenzyl-O-pivaloylhydroxylamine "
                "(9.09 g, 30.6 mmol), copper(II) acetate (46 mg, 0.25 mmol), (S)-DTBM-SEGPHOS "
                "(330 mg, 0.28 mmol), triphenylphosphine (74 mg, 0.28 mmol), "
                "2,3,3-trimethyl-1-butene (2.50 g, 25.5 mmol, limiting reagent), and THF (25 mL, "
                "dried, via syringe).\n"
                "2. dimethoxy(methyl)silane (5.41 g, 51.4 mmol) was added dropwise via syringe "
                "over 10 min with the flask in a 23 degC water bath (blue on addition, orange by "
                "10 min), then the mixture was heated to 40 degC with an oil bath and stirred for "
                "an additional 12 h.\n"
                "3. The mixture was cooled to 23 degC, quenched with 50 mL saturated aqueous "
                "sodium bicarbonate, and extracted with ethyl acetate (3 x 50 mL); the combined "
                "organics were concentrated on a rotary evaporator (35 degC, 50 mmHg).\n"
                "4. The residue was purified by silica chromatography (1% EtOAc/hexanes, 2500 "
                "mL) to give the title compound "
                "`C[C@@H](CN(CC1=CC=CC=C1)CC2=CC=CC=C2)C(C)(C)C` (6.54 g, 87% yield, 97% purity "
                "by quantitative 1H NMR, 90% ee by chiral SFC (Chiralpak AD-H); "
                "[alpha]D = -114 (c = 1.0, CHCl3)).\n\n"
                f"Source: {_LIU_PROJECT}. Experimenter: Richard Y. Liu, MIT."
            ),
            "operator": "Richard Y. Liu",
            "project": _LIU_PROJECT,
            "temperature_c": 40.0,
            "time_h": 12.0,
        }
    )
    return records


_SANTANILLA_PROJECT = "Science 2015, 347, 49-53 (DOI 10.1126/science.1259203), Experiment 2"
_SANTANILLA_PROCEDURE_HEADER = (
    "Experiment 2. 1536-Well Plate Screening of Pd Cross-Coupling Reactions of "
    "3-Bromopyridine 22 with 16 Nucleophiles (16 Precatalysts, 6 Bases). A 1536-well plate "
    "experiment examining the reactivity of 3-bromopyridine 22 with 16 different classes of "
    "nucleophiles under 96 Pd cross-coupling reaction conditions was run at 100 nanomolar scale "
    "by dosing from a 384-well plate containing stock solutions of the starting materials and "
    "reagents into a 1536-well plate by Mosquito. Stock solutions of each of the reaction "
    "components were prepared as follows: Pd-precatalysts (0.04 M in DMSO), aryl halide (0.4 M "
    "in DMSO), nucleophiles (0.6 M in DMSO), and base (0.8 M in DMSO). The plate was allowed to "
    "sit at room temperature for 22 hours, then quenched with acetic acid/biphenyl internal "
    "standard and analyzed by UPLC (real, quoted from the paper's SI)."
)

# The 4 highest-yielding real wells (one per additional nucleophile class) from the same
# Experiment 2 screen, pulled directly from 1259203_Datafiles.xlsx ("Data S2- Experiment 2").
_SANTANILLA_WELLS = [
    {
        "id": "santanilla-orgsyn-aniline-well-D6",
        "well": "D6",
        "nucleophile_smiles": "NC1=CC=CC=C1",
        "nucleophile_name": "aniline (nucleophile class S2)",
        "catalyst_name": "DTBPF Pd G3 38",
        "catalyst_smiles": (
            "CS(O[Pd]1([P](C(C)(C)C)(C(C)(C)C)C2=CC=CC2[Fe]C3C(P(C(C)(C)C)C(C)(C)C)=CC=C3)"
            "C4=CC=CC=C4C5=C([NH2]1)C=CC=C5)(=O)=O"
        ),
        "base_name": "P2Et 29",
        "base_smiles": "CN(C)P(N(C)C)(N(C)C)=NP(N(C)C)(N(C)C)=NCC",
        "product_smiles": "C1(NC2=CN=CC=C2)=CC=CC=C1",
        "product_name": "N-phenylpyridin-3-amine",
        "reaction_class": "buchwald-hartwig-amination",
        "yield_percent": 60.72,
    },
    {
        "id": "santanilla-orgsyn-boronate-well-Y36",
        "well": "Y36",
        "nucleophile_smiles": "CC(C(C)(C)O1)(C)OB1C(C=N2)=CN2CC3=CC=CC=C3",
        "nucleophile_name": "N-benzylpyrazole boronic acid pinacol ester (nucleophile class S14)",
        "catalyst_name": "Aphos Pd G3 35",
        "catalyst_smiles": (
            "NC(C=C1)=CC=C1[P]([Pd]2(OS(C)(=O)=O)C3=CC=CC=C3C4=C([NH2]2)C=CC=C4)"
            "(C(C)(C)C)C(C)(C)C"
        ),
        "base_name": "P2Et 29",
        "base_smiles": "CN(C)P(N(C)C)(N(C)C)=NP(N(C)C)(N(C)C)=NCC",
        "product_smiles": "C1(CN2C=C(C3=CN=CC=C3)C=N2)=CC=CC=C1",
        "product_name": "1-benzyl-4-(pyridin-3-yl)pyrazole",
        "reaction_class": "suzuki-miyaura",
        "yield_percent": 119.43,
    },
    {
        "id": "santanilla-orgsyn-alkyne-well-AF21",
        "well": "AF21",
        "nucleophile_smiles": "CCCCC1=CC=C(C#C)C=C1",
        "nucleophile_name": "1-butyl-4-ethynylbenzene (nucleophile class S16)",
        "catalyst_name": "BrettPhos Pd G3 41",
        "catalyst_smiles": (
            "CS(O[Pd]1([P](C2CCCCC2)(C3CCCCC3)C4=C(C5=C(C(C)C)C=C(C(C)C)C=C5C(C)C)"
            "C(OC)=CC=C4OC)C6=CC=CC=C6C7=C([NH2]1)C=CC=C7)(=O)=O"
        ),
        "base_name": "BTMG 26",
        "base_smiles": "CN(C)/C(N(C)C)=N\\C(C)(C)C",
        "product_smiles": "CCCCC1=CC=C(C#CC2=CN=CC=C2)C=C1",
        "product_name": "3-((4-butylphenyl)ethynyl)pyridine",
        "reaction_class": "sonogashira",
        "yield_percent": 86.89,
    },
    {
        "id": "santanilla-orgsyn-alcohol-well-R36",
        "well": "R36",
        "nucleophile_smiles": "OCCCC1=CC=CC=C1",
        "nucleophile_name": "3-phenyl-1-propanol (nucleophile class S9)",
        "catalyst_name": "tBuBrettPhos Pd G3 43",
        "catalyst_smiles": (
            "CS(O[Pd]1([P](C(C)(C)C)(C(C)(C)C)C2=C(C3=C(C(C)C)C=C(C(C)C)C=C3C(C)C)"
            "C(OC)=CC=C2OC)C4=CC=CC=C4C5=C([NH2]1)C=CC=C5)(=O)=O"
        ),
        "base_name": "P2Et 29",
        "base_smiles": "CN(C)P(N(C)C)(N(C)C)=NP(N(C)C)(N(C)C)=NCC",
        "product_smiles": "C1(CCCOC2=CN=CC=C2)=CC=CC=C1",
        "product_name": "3-(3-phenylpropoxy)pyridine",
        "reaction_class": "buchwald-hartwig-etherification",
        "yield_percent": 29.49,
    },
]

_ARYL_HALIDE_SMILES = "BrC1=CN=CC=C1"  # 3-bromopyridine, fixed electrophile for Experiment 2


def _santanilla_records() -> list[dict[str, Any]]:
    records = []
    for i, well in enumerate(_SANTANILLA_WELLS):
        timestamp = _BASE_TIME + timedelta(hours=48 + i * 4)
        yield_note = (
            " (UPLC peak-area-ratio yield relative to an internal standard; can exceed 100% "
            "due to detector response differences between product and standard, as reported "
            "in the paper's own analysis -- not clipped here)."
            if well["yield_percent"] > 100
            else "."
        )
        records.append(
            {
                "id": well["id"],
                "timestamp": _iso(timestamp),
                "reactants": [
                    {"smiles": _ARYL_HALIDE_SMILES, "role": "reactant"},
                    {"smiles": well["nucleophile_smiles"], "role": "reactant"},
                    {
                        "smiles": well["catalyst_smiles"],
                        "role": "catalyst",
                        "name": well["catalyst_name"],
                    },
                    {
                        "smiles": well["base_smiles"],
                        "role": "reagent",
                        "name": well["base_name"],
                    },
                ],
                "products": [
                    {
                        "smiles": well["product_smiles"],
                        "yield_percent": well["yield_percent"],
                    }
                ],
                "procedure": (
                    f"{_SANTANILLA_PROCEDURE_HEADER}\n\n"
                    f"This record narrates well {well['well']} of that same 1536-well plate: "
                    f"3-bromopyridine (22) was cross-coupled with {well['nucleophile_name']} "
                    f"using precatalyst {well['catalyst_name']} and base {well['base_name']}, "
                    f"giving {well['product_name']} (`{well['product_smiles']}`) in "
                    f"{well['yield_percent']:.1f}% yield{yield_note} This was the "
                    f"highest-yielding real condition recorded for this nucleophile class in "
                    "the published dataset.\n\n"
                    f"Source: {_SANTANILLA_PROJECT}."
                ),
                "operator": "Santanilla et al. (Merck)",
                "project": _SANTANILLA_PROJECT,
                "time_h": 22.0,
                "reactionClass": well["reaction_class"],
            }
        )
    return records


def real_uspto_style_records() -> list[dict[str, Any]]:
    """All real, cited free-text ELN records: 3 Liu (Org. Synth.) + 4 Santanilla (Science).

    Small and entirely real by design -- see module docstring for why this corpus does not
    reach the 10,000-record scale originally targeted for the unstructured ELN source.
    """
    return _liu_records() + _santanilla_records()
