"""The source eval's answer key, pinned.

Chemclaw3's `data/evals/probes/sources.yaml` quotes these answers in its `direction:` lines. A
change to the seeded data that moves one fails here, and the probe file has to move with it.
"""

from app.eln.source_eval import QUESTIONS, answer_key

PINNED = {
    "sq-01": {
        "wells": 264,
        "at_least_50": 19
    },
    "sq-02": {
        "AdBrettPhos": 28.2,
        "XPhos": 11.1,
        "tBuBrettPhos": 30.0,
        "tBuXPhos": 34.2
    },
    "sq-03": {
        "max": 91.39,
        "above_10": 236
    },
    "sq-04": {
        "bromide": 35.7,
        "chloride": 6.0,
        "iodide": 44.4
    },
    "sq-05": {
        "BTMG": 34.2,
        "MTBD": 41.8,
        "P2Et": 25.2
    },
    "sq-06": 236,
    "sq-07": {
        "yield": 93.67,
        "names": [
            "2a, Boronic Acid",
            "XPhos",
            "NaOH"
        ],
        "solvent": "MeCN"
    },
    "sq-08": {
        "no_ligand": 29.6,
        "XPhos": 46.8
    },
    "sq-09": {
        "DMF": 371,
        "MeCN": 542
    },
    "sq-10": {
        "CsF": 70.9,
        "Et3N": 74.2,
        "K3PO4": 68.1,
        "KOH": 77.9,
        "LiOtBu": 82.4,
        "NaHCO3": 75.0,
        "NaOH": 83.9,
        "no base": 63.2
    },
    "sq-11": {
        "productive": 35,
        "best": [
            "AdBrettPhos Pd G3 45",
            "BTMG 26",
            47.47
        ]
    },
    "sq-12": {
        "amidation": [
            "AdBrettPhos Pd G3 45",
            "BTMG 26",
            47.47
        ],
        "sulfonamidation": [
            "tBuBrettPhos Pd G3 43",
            "P2Et 29",
            27.65
        ]
    },
    "sq-13": [
        "4-(trifluoromethyl)benzenesulfonyl fluoride",
        "MTBD",
        69.0
    ],
    "sq-14": {
        "BTMG": 46.8,
        "BTPP": 50.2,
        "DBU": 32.1,
        "MTBD": 40.9
    },
    "sq-15": {
        "4-biphenylmethanol": 52.0,
        "4-phenylbutan-2-ol": 54.0,
        "N-Boc-trans-4-hydroxy-L-proline methyl ester": 42.7,
        "cis-3-(benzyloxy)cyclobutanol": 21.2
    },
    "sq-16": {
        "recorded": 80,
        "at_least_70": 12
    },
    "sq-17": {
        "recorded": 192,
        "mean": 5.5
    },
    "sq-18": {
        "reactions": 1370,
        "at_least_80": 213
    },
    "sq-19": [
        "ord-buchwald-hartwig-1",
        "ord-buchwald-hartwig-2",
        "ord-fischer-esterification-1",
        "ord-fischer-esterification-2",
        "ord-snar-piperidine-1",
        "ord-snar-piperidine-2",
        "ord-suzuki-biphenyl-1",
        "ord-suzuki-biphenyl-2"
    ],
    "sq-20": [
        "ord-grignard-benzhydrol-1",
        "ord-grignard-benzhydrol-2",
        "ord-wittig-styrene-1",
        "ord-wittig-styrene-2"
    ],
    "ns-01": {
        "uspto-suzuki-biphenyl-2": 92.5,
        "uspto-reductive-amination-2": 79.5,
        "uspto-grignard-benzhydrol-2": 74.5,
        "uspto-wittig-styrene-2": 70.5,
        "uspto-buchwald-hartwig-2": 88.5,
        "uspto-epoxide-opening-2": 77.5
    },
    "ns-02": {
        "entries": 5,
        "failed": [
            [
                "uspto-boc-deprotection-failed",
                "TFA cleavage stalled; starting material recovered by TLC/LCMS."
            ]
        ]
    },
    "ns-03": [
        "ord-buchwald-hartwig-2",
        88.0
    ],
    "ns-04": {
        "eln-json": [
            89.5,
            92.5
        ],
        "eln-ord": [
            90.0,
            92.0
        ]
    },
    "ns-05": {
        "records": 3955,
        "mean": 33.1
    },
    "ns-06": [
        "santanilla-orgsyn-boronate-well-Y36"
    ],
    "ns-07": {
        "entries": 6,
        "mean": 77.5
    },
    "ns-08": {
        "records": 24,
        "mean": 83.2
    },
    "ns-09": [
        "uspto-amide-coupling-2",
        "uspto-boc-deprotection-2",
        "uspto-boc-deprotection-failed",
        "uspto-fischer-esterification-2",
        "uspto-friedel-crafts-acylation-2",
        "uspto-snar-piperidine-2",
        "uspto-sonogashira-2"
    ],
    "ns-10": {
        "liu-orgsyn-procedure-1": 93.5,
        "liu-orgsyn-procedure-2": 86.0,
        "liu-orgsyn-procedure-3": 87.0
    }
}


def test_every_question_has_a_pinned_answer() -> None:
    assert set(QUESTIONS) == set(PINNED)


def test_the_answer_key_is_what_the_probe_file_quotes() -> None:
    assert answer_key() == PINNED
