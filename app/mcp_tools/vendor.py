"""Building-block catalog: the plain, testable logic behind the vendor MCP tool.

Mirrors the split Chemclaw3 itself uses for mcp-molfp/mcp-rxnfp (`mcp_servers/README.md`):
capability logic lives here as ordinary Python, independent of MCP; `vendor_server.py` is the
thin FastMCP wrapper. A small deterministic in-memory catalog — some entries share SMILES with
the ELN fixtures (`app/eln/fixtures_data.py`) so an agent can plausibly look up pricing for a
reagent it just read about in a synced ELN note.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildingBlock:
    catalog_id: str
    name: str
    smiles: str
    vendor: str
    price_usd: float
    pack_size: str
    lead_time_days: int
    in_stock: bool


_CATALOG: list[BuildingBlock] = [
    BuildingBlock("VC-00101", "4-Bromoanisole", "COc1ccc(Br)cc1", "MockChem", 42.50, "25 g", 2, True),
    BuildingBlock("VC-00102", "Phenylboronic acid", "OB(O)c1ccccc1", "MockChem", 38.00, "25 g", 2, True),
    BuildingBlock("VC-00103", "Benzoic acid", "O=C(O)c1ccccc1", "MockChem", 21.75, "100 g", 1, True),
    BuildingBlock("VC-00104", "Aniline", "Nc1ccccc1", "MockChem", 24.00, "100 g", 1, True),
    BuildingBlock("VC-00105", "Benzaldehyde", "O=Cc1ccccc1", "MockChem", 19.90, "100 g", 1, True),
    BuildingBlock("VC-00106", "Methylamine (2M in THF)", "CN", "MockChem", 55.00, "100 mL", 3, True),
    BuildingBlock("VC-00107", "Bromobenzene", "Brc1ccccc1", "MockChem", 27.30, "100 g", 1, True),
    BuildingBlock("VC-00108", "Acetyl chloride", "CC(Cl)=O", "MockChem", 33.10, "100 g", 2, True),
    BuildingBlock("VC-00109", "4-Bromotoluene", "Cc1ccc(Br)cc1", "MockChem", 29.60, "25 g", 3, True),
    BuildingBlock("VC-00110", "Morpholine", "C1COCCN1", "MockChem", 18.40, "100 g", 1, True),
    BuildingBlock("VC-00111", "Iodobenzene", "Ic1ccccc1", "MockChem", 45.00, "25 g", 4, False),
    BuildingBlock("VC-00112", "Phenylacetylene", "C#Cc1ccccc1", "MockChem", 61.20, "5 g", 5, False),
    BuildingBlock("VC-00113", "Styrene oxide", "c1ccc(C2CO2)cc1", "MockChem", 40.00, "25 g", 2, True),
    BuildingBlock("VC-00114", "Sodium azide", "[N-]=[N+]=[N-].[Na+]", "MockChem", 15.50, "100 g", 1, True),
    BuildingBlock(
        "VC-00115",
        "tert-Butyl 4-aminopiperidine-1-carboxylate",
        "CC(C)(C)OC(=O)N1CCC(N)CC1",
        "MockChem",
        88.00,
        "5 g",
        6,
        False,
    ),
    BuildingBlock("VC-00116", "4-Fluoronitrobenzene", "O=[N+]([O-])c1ccc(F)cc1", "MockChem", 22.00, "100 g", 1, True),
    BuildingBlock("VC-00117", "Piperidine", "C1CCNCC1", "MockChem", 16.80, "500 g", 1, True),
    BuildingBlock("VC-00118", "Ethanol (anhydrous)", "CCO", "MockChem", 12.00, "1 L", 1, True),
    BuildingBlock("VC-00119", "Triethylamine", "CCN(CC)CC", "MockChem", 20.50, "500 mL", 1, True),
    BuildingBlock("VC-00120", "Sulfuric acid (conc.)", "OS(=O)(=O)O", "MockChem", 14.25, "500 mL", 1, True),
]

_BY_CATALOG_ID = {block.catalog_id: block for block in _CATALOG}


def search(query: str) -> list[BuildingBlock]:
    """Case-insensitive substring match over name and SMILES — the whole "search" this mock does."""
    needle = query.strip().lower()
    if not needle:
        return []
    return [
        block
        for block in _CATALOG
        if needle in block.name.lower() or needle in block.smiles.lower()
    ]


def price(catalog_id: str) -> BuildingBlock | None:
    return _BY_CATALOG_ID.get(catalog_id)
