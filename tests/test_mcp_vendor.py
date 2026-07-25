from app.mcp_tools import vendor
from app.mcp_tools.vendor_server import get_price, search_building_blocks


def test_search_matches_by_name_substring():
    results = vendor.search("bromoanisole")
    assert len(results) == 1
    assert results[0].catalog_id == "VC-00101"


def test_search_matches_by_smiles_substring():
    results = vendor.search("c1ccccc1")
    assert len(results) > 1


def test_search_empty_query_returns_nothing():
    assert vendor.search("   ") == []


def test_price_lookup_known_id():
    block = vendor.price("VC-00103")
    assert block is not None
    assert block.name == "Benzoic acid"


def test_price_lookup_unknown_id_returns_none():
    assert vendor.price("does-not-exist") is None


def test_tool_wrappers_serialize_to_plain_dicts():
    results = search_building_blocks("aniline")
    assert results and results[0]["catalog_id"] == "VC-00104"

    priced = get_price("VC-00104")
    assert priced["price_usd"] == 24.00

    missing = get_price("nope")
    assert "error" in missing
