"""The answer key for Chemclaw3's source eval (`data/evals/probes/sources.yaml` there).

Two halves, both computed from the same record dicts `seed.py` writes to disk:

- **`sq-*`**: a structured filter over the ORD records (curated plus the real HTE datasets, at full
  scale). Each reads only what Chemclaw3's `OrdJsonAdapter` keeps: input identifiers, the headline
  yield, the temperature setpoint, the creation date and the procedure notes. Never `datasetId`
  or `reactionClass`, which the adapter drops.
- **`ns-*`**: a question naming one source, the free-text ELN (`eln-json`) or the structured
  export (`eln-ord`), reading what `JsonExportAdapter` keeps (project, operator, outcome, failure
  reason, per-product yield) or what the ORD provenance carries (the DOI, the recording person).

The probe file quotes these answers in its `direction:` lines; `tests/test_source_eval.py` pins
them, so a change to the seeded data that moves an answer fails here first.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime
from typing import Any, NamedTuple

from app.eln.fixtures_data import ord_style_records, uspto_style_records
from app.eln.real_hte import all_real_hte_records
from app.eln.real_procedures import real_uspto_style_records

Record = dict[str, Any]


class Corpus(NamedTuple):
    """What the mock seeds: the structured ORD records and the free-text ELN entries."""

    ord: list[Record]
    free_text: list[Record]

# The compounds the questions name, as the records spell them.
BROMOANISOLE = "BrC1=CC=C(OC)C=C1"
CHLOROPYRIDINE_2 = "ClC1=NC=CC=C1"
IODO_CF3_BENZENE = "IC1=CC=C(C(F)(F)F)C=C1"
METHYLANILINE = "Cc1ccc(N)cc1"
MTBD = "CN1CCCN2C1=NCCC2"
PHENYLBUTANOL = "c1ccccc1CCC(O)C"
BENZAMIDE = "NC(C1=CC=CC=C1)=O"
BENZENESULFONAMIDE = "NS(C1=CC=CC=C1)(=O)=O"
CHLOROQUINOLINE_6 = "Clc1ccc2ncccc2c1"
IODOQUINOLINE_6 = "Ic1ccc2ncccc2c1"

#: The four Buchwald ligands of the Ahneman/Doyle campaign, named as a chemist would.
BH_LIGANDS = {
    "CC(C)C(C=C(C(C)C)C=C1C(C)C)=C1C2=C(P(C3CCCCC3)C4CCCCC4)C=CC=C2": "XPhos",
    "CC(C)C(C=C(C(C)C)C=C1C(C)C)=C1C2=C(P(C(C)(C)C)C(C)(C)C)C=CC=C2": "tBuXPhos",
    "CC(C)C(C=C(C(C)C)C=C1C(C)C)=C1C2=C(P(C(C)(C)C)C(C)(C)C)C(OC)=CC=C2OC": "tBuBrettPhos",
    (
        "CC(C)C(C=C(C(C)C)C=C1C(C)C)=C1C2=C(P([C@@]3(C[C@@H]4C5)C[C@H](C4)C[C@H]5C3)"
        "[C@]6(C7)C[C@@H](C[C@@H]7C8)C[C@@H]8C6)C(OC)=CC=C2OC"
    ): "AdBrettPhos",
}

#: The three phosphazene/guanidine/amidine bases of the same campaign, one per plate.
BH_BASES = {
    "CN(C)P(N(C)C)(N(C)C)=NP(N(C)C)(N(C)C)=NCC": "P2Et",
    MTBD: "MTBD",
    "CC(C)(C)/N=C(N(C)C)/N(C)C": "BTMG",
}

#: The sulfonyl fluorides and bases of the Nielsen deoxyfluorination screen.
NIELSEN_FLUORIDES = {
    "Clc1ccc(S(=O)(=O)F)cc1": "4-chlorobenzenesulfonyl fluoride",
    "O=S(C1=CC=CC=N1)(F)=O": "PyFluor",
    "O=S(C1=CC=C(C(F)(F)F)C=C1)(F)=O": "4-(trifluoromethyl)benzenesulfonyl fluoride",
    "O=S(C1=CC=C([N+]([O-])=O)C=C1)(F)=O": "4-nitrobenzenesulfonyl fluoride",
    "C(C(C(F)(F)S(=O)(=O)F)(F)F)(C(F)(F)F)(F)F": "perfluorobutanesulfonyl fluoride",
}
NIELSEN_BASES = {
    "N\\2=C1\\N(CCCCC1)CCC/2": "DBU",
    MTBD: "MTBD",
    "CC(C)(C)N=C(N(C)C)N(C)C": "BTMG",
    "CC(C)(C)N=P(N1CCCC1)(N2CCCC2)N3CCCC3": "BTPP",
}
NIELSEN_ALCOHOLS = {
    PHENYLBUTANOL: "4-phenylbutan-2-ol",
    "c1ccccc1-c2ccc(CO)cc2": "4-biphenylmethanol",
    "O[C@@H]1C[C@H](OCC2=CC=CC=C2)C1": "cis-3-(benzyloxy)cyclobutanol",
    "O[C@H]1C[C@@H](C(OC)=O)N(C(OC(C)(C)C)=O)C1": "N-Boc-trans-4-hydroxy-L-proline methyl ester",
}


def seeded_ord_records() -> list[Record]:
    """Every ORD record the mock seeds at full scale, in seeding order."""
    records = list(ord_style_records())
    for dataset in all_real_hte_records().values():
        records.extend(dataset)
    return records


def seeded_free_text_records() -> list[Record]:
    """Every free-text (`eln-json`) record the mock seeds, in seeding order."""
    return [*uspto_style_records(), *real_uspto_style_records()]


def _identifiers(record: Record, role: str | None = None) -> list[str]:
    """Every input identifier value (SMILES or NAME), optionally of one ORD reaction role."""
    return [
        identifier["value"]
        for reaction_input in record["inputs"].values()
        for component in reaction_input["components"]
        if role is None or component["reactionRole"] == role
        for identifier in component["identifiers"]
    ]


def _has(record: Record, value: str, role: str | None = None) -> bool:
    return value in _identifiers(record, role)


def _yield(record: Record) -> float | None:
    for measurement in record["outcomes"][0]["products"][0].get("measurements", []):
        if measurement["type"] == "YIELD":
            return float(measurement["percentage"]["value"])
    return None


def _created(record: Record) -> date:
    stamp = record["provenance"]["recordCreated"]["time"]["value"]
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()


def _temperature(record: Record) -> float | None:
    setpoint = record.get("conditions", {}).get("temperature", {}).get("setpoint")
    return None if setpoint is None else float(setpoint["value"])


def _notes(record: Record) -> str:
    return str(record.get("notes", {}).get("procedureDetails", ""))


def _named(record: Record, names: dict[str, str]) -> str | None:
    """The first input identifier `names` knows, by its name."""
    return next((names[v] for v in _identifiers(record) if v in names), None)


def _yields(records: Iterable[Record]) -> list[float]:
    return [y for y in (_yield(r) for r in records) if y is not None]


def _mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 1)


def _mean_by(records: Iterable[Record], key: Callable[[Record], str | None]) -> dict[str, float]:
    groups: dict[str, list[float]] = defaultdict(list)
    for record in records:
        group, value = key(record), _yield(record)
        if group is not None and value is not None:
            groups[group].append(value)
    return {group: _mean(values) for group, values in sorted(groups.items())}


def _best(records: Iterable[Record]) -> Record:
    """The highest-yielding record; the first seeded wins a tie, so the answer is stable."""
    return max(records, key=lambda r: _yield(r) or 0.0)


def _bh(records: list[Record]) -> list[Record]:
    """The Buchwald-Hartwig aminations with 4-methylaniline (the Ahneman/Doyle wells)."""
    return [r for r in records if _has(r, METHYLANILINE, "REACTANT")]


def _suzuki(records: list[Record], quinoline: str) -> list[Record]:
    return [r for r in records if _has(r, quinoline, "REACTANT") and "flow screening" in _notes(r)]


def _solvent(record: Record) -> str:
    """The Suzuki flow screen's solvent, which only the procedure notes carry."""
    return _notes(record).rsplit(" in ", 1)[1].split(".", 1)[0]


def _halogen(smiles: str) -> str:
    """The aryl halide's leaving group; every Ahneman/Doyle SMILES starts with the halogen."""
    return next(name for prefix, name in (("Cl", "chloride"), ("Br", "bromide"), ("I", "iodide"))
                if smiles.startswith(prefix))


def sq01(corpus: Corpus) -> Any:
    records = corpus.ord
    wells = [r for r in _bh(records) if _has(r, BROMOANISOLE)]
    return {"wells": len(wells), "at_least_50": sum(y >= 50 for y in _yields(wells))}


def sq02(corpus: Corpus) -> Any:
    records = corpus.ord
    wells = [r for r in _bh(records) if _has(r, BROMOANISOLE)]
    return _mean_by(wells, lambda r: _named(r, BH_LIGANDS))


def sq03(corpus: Corpus) -> Any:
    records = corpus.ord
    yields = _yields(r for r in _bh(records) if _has(r, CHLOROPYRIDINE_2))
    return {"max": max(yields), "above_10": sum(y > 10 for y in yields)}


def sq04(corpus: Corpus) -> Any:
    records = corpus.ord
    def halide(record: Record) -> str:
        return _halogen(_identifiers(record, "REACTANT")[0])

    groups: dict[str, list[float]] = defaultdict(list)
    for record in _bh(records):
        groups[halide(record)].append(_yield(record) or 0.0)
    return {name: round(statistics.median(values), 1) for name, values in sorted(groups.items())}


def sq05(corpus: Corpus) -> Any:
    records = corpus.ord
    wells = [r for r in _bh(records) if _has(r, IODO_CF3_BENZENE)]
    return _mean_by(wells, lambda r: _named(r, BH_BASES))


def sq06(corpus: Corpus) -> Any:
    records = corpus.ord
    return sum(y == 0 for y in _yields(_bh(records)))


def sq07(corpus: Corpus) -> Any:
    records = corpus.ord
    best = _best(_suzuki(records, CHLOROQUINOLINE_6))
    named = [
        identifier["value"]
        for reaction_input in best["inputs"].values()
        for component in reaction_input["components"]
        for identifier in component["identifiers"]
        if identifier["type"] == "NAME"
    ]
    return {"yield": _yield(best), "names": named, "solvent": _solvent(best)}


def sq08(corpus: Corpus) -> Any:
    records = corpus.ord
    flow = [r for r in records if "flow screening" in _notes(r)]
    no_ligand = [r for r in flow if "ligand" not in r["inputs"]]
    xphos = [r for r in flow if _has(r, "XPhos", "CATALYST")]
    return {"no_ligand": _mean(_yields(no_ligand)), "XPhos": _mean(_yields(xphos))}


def sq09(corpus: Corpus) -> Any:
    records = corpus.ord
    flow = [r for r in records if "flow screening" in _notes(r)]
    return {
        solvent: sum(y > 50 for y in _yields(r for r in flow if _solvent(r) == solvent))
        for solvent in ("DMF", "MeCN")
    }


def sq10(corpus: Corpus) -> Any:
    records = corpus.ord
    wells = [r for r in _suzuki(records, IODOQUINOLINE_6) if _has(r, "2a, Boronic Acid")]
    base_names = {"NaOH", "NaHCO3", "CsF", "K3PO4", "KOH", "LiOtBu", "Et3N"}
    return _mean_by(
        wells, lambda r: next((v for v in _identifiers(r) if v in base_names), "no base")
    )


def _santanilla(records: list[Record], nucleophile: str) -> list[Record]:
    return [r for r in records if _has(r, nucleophile, "REACTANT")]


def _precatalyst(record: Record) -> str:
    return _identifiers(record, "CATALYST")[1]


def _base_name(record: Record) -> str:
    return _identifiers(record, "REAGENT")[1]


def sq11(corpus: Corpus) -> Any:
    records = corpus.ord
    wells = _santanilla(records, BENZAMIDE)
    productive = [r for r in wells if (_yield(r) or 0) > 0]
    best = _best(wells)
    return {
        "productive": len(productive),
        "best": [_precatalyst(best), _base_name(best), _yield(best)],
    }


def sq12(corpus: Corpus) -> Any:
    records = corpus.ord
    out = {}
    for label, nucleophile in (("amidation", BENZAMIDE), ("sulfonamidation", BENZENESULFONAMIDE)):
        best = _best(_santanilla(records, nucleophile))
        out[label] = [_precatalyst(best), _base_name(best), _yield(best)]
    return out


def _nielsen(records: list[Record]) -> list[Record]:
    return [r for r in records if _named(r, NIELSEN_FLUORIDES) is not None]


def sq13(corpus: Corpus) -> Any:
    records = corpus.ord
    best = _best(r for r in _nielsen(records) if _has(r, PHENYLBUTANOL))
    return [_named(best, NIELSEN_FLUORIDES), _named(best, NIELSEN_BASES), _yield(best)]


def sq14(corpus: Corpus) -> Any:
    records = corpus.ord
    return _mean_by(_nielsen(records), lambda r: _named(r, NIELSEN_BASES))


def sq15(corpus: Corpus) -> Any:
    records = corpus.ord
    return _mean_by(_nielsen(records), lambda r: _named(r, NIELSEN_ALCOHOLS))


def sq16(corpus: Corpus) -> Any:
    records = corpus.ord
    june = [r for r in records if (_created(r).year, _created(r).month) == (2023, 6)]
    return {"recorded": len(june), "at_least_70": sum(y >= 70 for y in _yields(june))}


def sq17(corpus: Corpus) -> Any:
    records = corpus.ord
    may = [r for r in records if (_created(r).year, _created(r).month) == (2023, 5)]
    return {"recorded": len(may), "mean": _mean(_yields(may))}


def sq18(corpus: Corpus) -> Any:
    records = corpus.ord
    with_mtbd = [r for r in records if _has(r, MTBD, "REAGENT")]
    return {"reactions": len(with_mtbd), "at_least_80": sum(y >= 80 for y in _yields(with_mtbd))}


def sq19(corpus: Corpus) -> Any:
    records = corpus.ord
    hot = [r for r in records if (_temperature(r) or 0) > 70 and (_yield(r) or 0) > 85]
    return sorted(r["reactionId"] for r in hot)


def sq20(corpus: Corpus) -> Any:
    records = corpus.ord
    january = [r for r in records if _created(r) >= date(2024, 1, 1)]
    return sorted(r["reactionId"] for r in january if (_yield(r) or 0) < 75)


def _free_text_yield(record: Record) -> float:
    return float(record["products"][0]["yield_percent"])


def _ours(record: Record) -> bool:
    """A curated ORD record, as opposed to a published-dataset import (told apart by provenance)."""
    return "doi" not in record["provenance"]


def ns01(corpus: Corpus) -> Any:
    free_text = corpus.free_text
    beta = [r for r in free_text if r.get("project") == "PROJ-BETA"]
    return {r["id"]: _free_text_yield(r) for r in beta}


def ns02(corpus: Corpus) -> Any:
    free_text = corpus.free_text
    fischer = [r for r in free_text if r["operator"] == "K. Fischer"]
    failed = [r for r in fischer if r.get("outcome") == "failure"]
    return {
        "entries": len(fischer),
        "failed": [[r["id"], r["failure_reason"]] for r in failed],
    }


def ns03(corpus: Corpus) -> Any:
    records = corpus.ord
    best = _best(r for r in records if _ours(r) and r["reactionId"].startswith("ord-buchwald"))
    return [best["reactionId"], _yield(best)]


def ns04(corpus: Corpus) -> Any:
    records, free_text = corpus
    return {
        "eln-json": [_free_text_yield(r) for r in free_text if r["id"].startswith("uspto-suzuki")],
        "eln-ord": _yields(r for r in records if r["reactionId"].startswith("ord-suzuki")),
    }


def ns05(corpus: Corpus) -> Any:
    records = corpus.ord
    doyle = [r for r in records if r["provenance"].get("doi") == "10.1126/science.aar5169"]
    return {"records": len(doyle), "mean": _mean(_yields(doyle))}


def ns06(corpus: Corpus) -> Any:
    free_text = corpus.free_text
    return sorted(r["id"] for r in free_text if _free_text_yield(r) > 100)


def ns07(corpus: Corpus) -> Any:
    free_text = corpus.free_text
    alpha = [r for r in free_text if r.get("project") == "PROJ-ALPHA"]
    return {"entries": len(alpha), "mean": _mean([_free_text_yield(r) for r in alpha])}


def ns08(corpus: Corpus) -> Any:
    records = corpus.ord
    ours = [r for r in records if _ours(r)]
    return {"records": len(ours), "mean": _mean(_yields(ours))}


def ns09(corpus: Corpus) -> Any:
    free_text = corpus.free_text
    return sorted(r["id"] for r in free_text if not r.get("project"))


def ns10(corpus: Corpus) -> Any:
    free_text = corpus.free_text
    orgsyn = [r for r in free_text if "Org. Synth." in str(r.get("project"))]
    return {r["id"]: _free_text_yield(r) for r in orgsyn}


#: Question id to the function computing its answer. The ids are the probe ids in Chemclaw3.
QUESTIONS: dict[str, Callable[[Corpus], Any]] = {
    fn.__name__[:2] + "-" + fn.__name__[2:]: fn
    for fn in (
        sq01, sq02, sq03, sq04, sq05, sq06, sq07, sq08, sq09, sq10,
        sq11, sq12, sq13, sq14, sq15, sq16, sq17, sq18, sq19, sq20,
        ns01, ns02, ns03, ns04, ns05, ns06, ns07, ns08, ns09, ns10,
    )
}


def seeded_corpus() -> Corpus:
    """Everything the mock seeds at full scale."""
    return Corpus(seeded_ord_records(), seeded_free_text_records())


def answer_key() -> dict[str, Any]:
    """Every question's answer over the full seeded corpus."""
    corpus = seeded_corpus()
    return {question: compute(corpus) for question, compute in QUESTIONS.items()}
