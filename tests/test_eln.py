def test_startup_seeds_both_sources(client):
    json_entries = client.get("/eln/json/entries").json()
    ord_entries = client.get("/eln/ord/entries").json()
    assert len(json_entries) >= 20
    assert len(ord_entries) >= 20


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
    entries = client.get("/eln/ord/entries").json()
    for entry in entries:
        assert entry["reactionId"]
        assert isinstance(entry["inputs"], dict) and entry["inputs"]
        for reaction_input in entry["inputs"].values():
            assert reaction_input["components"]
            for component in reaction_input["components"]:
                smiles_ids = [i for i in component["identifiers"] if i["type"] == "SMILES"]
                assert smiles_ids
        assert entry["outcomes"][0]["products"][0]["identifiers"][0]["type"] == "SMILES"
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
