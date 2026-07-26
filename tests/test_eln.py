def test_startup_seeds_both_sources(client):
    json_entries = client.get("/eln/json/entries").json()
    ord_entries = client.get("/eln/ord/entries").json()
    # The `client` fixture caps each real HTE dataset to 5 rows for speed (see conftest.py);
    # full real-scale counts (thousands of real reactions) are covered by
    # test_real_hte_datasets_at_full_scale below, which bypasses the HTTP app entirely.
    assert len(json_entries) >= 30
    assert len(ord_entries) >= 50


def test_json_entries_match_json_export_adapter_shape(client):
    entries = client.get("/eln/json/entries").json()
    for entry in entries:
        assert isinstance(entry["id"], str) and entry["id"]
        assert "T" in entry["timestamp"] or "Z" in entry["timestamp"]
        assert isinstance(entry["reactants"], list) and entry["reactants"]
        for reactant in entry["reactants"]:
            assert reactant["smiles"]
        assert isinstance(entry["products"], list) and entry["products"]
        assert entry["products"][0]["smiles"]
        assert isinstance(entry["procedure"], str)
        assert entry["operator"]


def test_ord_entries_match_ord_adapter_shape(client):
    # A couple of the real HTE datasets (e.g. Suzuki-Miyaura flow HTE) carry a component
    # identified only by the source paper's own NAME/shorthand because no real SMILES was
    # published for it (see app/eln/real_hte.py) -- so identifiers are checked for presence
    # of any type (SMILES or NAME), not specifically SMILES, matching real ORD schema
    # flexibility. The curated fixtures still always provide SMILES.
    entries = client.get("/eln/ord/entries").json()
    for entry in entries:
        assert entry["reactionId"]
        assert isinstance(entry["inputs"], dict) and entry["inputs"]
        for reaction_input in entry["inputs"].values():
            assert reaction_input["components"]
            for component in reaction_input["components"]:
                assert component["identifiers"]
        product_identifiers = entry["outcomes"][0]["products"][0]["identifiers"]
        assert product_identifiers
        assert {i["type"] for i in product_identifiers} <= {"SMILES", "NAME"}
        created = entry["provenance"]["recordCreated"]["time"]["value"]
        assert created


def test_one_json_entry_is_an_explicit_failure(client):
    entries = client.get("/eln/json/entries").json()
    failures = [e for e in entries if e.get("outcome") == "failure"]
    assert len(failures) == 1
    assert failures[0]["failure_reason"]


def test_append_json_entry_is_stamped_after_all_existing(client):
    before = client.get("/eln/json/entries").json()
    latest_before = max(e["timestamp"] for e in before)

    response = client.post("/eln/json/entries")
    assert response.status_code == 201
    new_entry = response.json()

    after = client.get("/eln/json/entries").json()
    assert len(after) == len(before) + 1
    assert new_entry["timestamp"] > latest_before


def test_append_ord_entry_is_stamped_after_all_existing(client):
    before = client.get("/eln/ord/entries").json()

    def created(e):
        return e["provenance"]["recordCreated"]["time"]["value"]

    latest_before = max(created(e) for e in before)

    response = client.post("/eln/ord/entries")
    assert response.status_code == 201
    new_entry = response.json()

    after = client.get("/eln/ord/entries").json()
    assert len(after) == len(before) + 1
    assert created(new_entry) > latest_before


def test_reset_restores_original_fixture_counts(client):
    client.post("/eln/json/entries")
    client.post("/eln/ord/entries")
    counts = client.post("/eln/reset").json()

    after_json = client.get("/eln/json/entries").json()
    after_ord = client.get("/eln/ord/entries").json()
    assert len(after_json) == counts["eln_json"]
    assert len(after_ord) == counts["eln_ord"]


def test_get_single_entry_by_id(client):
    entries = client.get("/eln/json/entries").json()
    one_id = entries[0]["id"]
    response = client.get(f"/eln/json/entries/{one_id}")
    assert response.status_code == 200
    assert response.json()["id"] == one_id


def test_get_unknown_entry_404(client):
    response = client.get("/eln/json/entries/does-not-exist")
    assert response.status_code == 404


def test_real_hte_datasets_tagged_and_present(client):
    # Pre-existing curated fixtures (fixtures_data.py) predate the datasetId/reactionClass
    # tagging convention and are not required to carry it; only the new real HTE entries are.
    entries = client.get("/eln/ord/entries").json()
    by_dataset = {}
    for entry in entries:
        dataset_id = entry.get("datasetId")
        if dataset_id is None:
            continue
        assert entry["reactionClass"]
        by_dataset.setdefault(dataset_id, []).append(entry)

    expected_datasets = {
        "bh-amination-plate-p2et",
        "bh-amination-plate-mtbd",
        "bh-amination-plate-btmg",
        "suzuki-miyaura-flow-hte",
        "santanilla-amidation-screen",
        "santanilla-sulfonamidation-screen",
        "nielsen-deoxyfluorination-screen",
    }
    assert expected_datasets <= set(by_dataset)

    amidation = by_dataset["santanilla-amidation-screen"]
    assert all(e["reactionClass"] == "buchwald-hartwig-amidation" for e in amidation)
    for e in amidation:
        assert e["provenance"]["doi"] == "10.1126/science.1259203"


def test_real_hte_datasets_at_full_scale():
    """The real HTE datasets themselves (bypassing the HTTP app's test-speed cap)."""
    from app.eln.real_hte import all_real_hte_records

    grouped = all_real_hte_records()
    assert len(grouped["bh-amination-plate-p2et"]) > 1000
    assert len(grouped["bh-amination-plate-mtbd"]) > 1000
    assert len(grouped["bh-amination-plate-btmg"]) > 1000
    assert sum(
        len(v) for k, v in grouped.items() if k.startswith("bh-amination-plate-")
    ) == 3955
    assert len(grouped["suzuki-miyaura-flow-hte"]) == 5760
    assert len(grouped["santanilla-amidation-screen"]) == 96
    assert len(grouped["santanilla-sulfonamidation-screen"]) == 96
    assert len(grouped["nielsen-deoxyfluorination-screen"]) == 80

    total = sum(len(v) for v in grouped.values())
    assert total > 9900


def test_real_hte_records_match_ord_adapter_shape():
    from app.eln.real_hte import all_real_hte_records

    grouped = all_real_hte_records(max_per_dataset=3)
    for records in grouped.values():
        for entry in records:
            assert entry["reactionId"]
            assert isinstance(entry["inputs"], dict) and entry["inputs"]
            for reaction_input in entry["inputs"].values():
                assert reaction_input["components"]
                for component in reaction_input["components"]:
                    identifier_types = {i["type"] for i in component["identifiers"]}
                    assert identifier_types  # every component has at least one identifier
            assert entry["outcomes"][0]["products"][0]["measurements"][0]["type"] == "YIELD"
            assert entry["provenance"]["doi"]


def test_real_free_text_records_are_all_cited():
    from app.eln.real_procedures import real_uspto_style_records

    records = real_uspto_style_records()
    assert len(records) == 7
    for record in records:
        assert record["id"]
        assert record["reactants"]
        for reactant in record["reactants"]:
            assert reactant["smiles"]
        assert record["products"]
        assert "doi" in record["procedure"].lower() or "10.1" in record["procedure"]
        assert record["operator"]
