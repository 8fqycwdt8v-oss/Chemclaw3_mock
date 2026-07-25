import re

from tests.conftest import AUTH

_OUTPUT_RE = re.compile(r"energy=(-?\d+\.\d+) converged=(True|False)")


def _launch(client, *, smiles="CCO", method="B3LYP", basis_set="def2-SVP", idempotency_key=None):
    headers = dict(AUTH)
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    body = {
        "pipeline": "qm-pipeline",
        "revision": "1.0",
        "params": {"smiles": smiles, "method": method, "basis_set": basis_set},
    }
    return client.post("/workflow/launch", json=body, headers=headers)


def test_launch_requires_auth(client):
    response = client.post("/workflow/launch", json={"params": {"smiles": "CCO"}})
    assert response.status_code == 401


def test_launch_rejects_wrong_token(client):
    response = client.post(
        "/workflow/launch",
        json={"params": {"smiles": "CCO"}},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_full_lifecycle_launch_poll_artifact(client):
    launch_response = _launch(client)
    assert launch_response.status_code == 200
    workflow_id = launch_response.json()["workflowId"]
    assert workflow_id

    # First poll: still running (polls_until_done=2 in the fixture).
    poll1 = client.get(f"/workflow/{workflow_id}", headers=AUTH)
    assert poll1.status_code == 200
    assert poll1.json()["workflow"]["status"] in ("SUBMITTED", "RUNNING")

    # Artifact not ready yet.
    early_artifact = client.get(f"/artifacts/{workflow_id}/qm_output.txt", headers=AUTH)
    assert early_artifact.status_code == 409

    # Second poll: reaches the terminal state.
    poll2 = client.get(f"/workflow/{workflow_id}", headers=AUTH)
    assert poll2.json()["workflow"]["status"] == "SUCCEEDED"

    artifact = client.get(f"/artifacts/{workflow_id}/qm_output.txt", headers=AUTH)
    assert artifact.status_code == 200
    match = _OUTPUT_RE.search(artifact.text)
    assert match is not None
    assert match.group(2) == "True"


def test_same_inputs_give_reproducible_energy(client):
    workflow_a = _launch(client, smiles="c1ccccc1", method="GFN2-xTB", basis_set="n/a").json()[
        "workflowId"
    ]
    workflow_b = _launch(
        client, smiles="c1ccccc1", method="GFN2-xTB", basis_set="n/a", idempotency_key="other-key"
    ).json()["workflowId"]
    for _ in range(2):
        client.get(f"/workflow/{workflow_a}", headers=AUTH)
        client.get(f"/workflow/{workflow_b}", headers=AUTH)
    text_a = client.get(f"/artifacts/{workflow_a}/qm_output.txt", headers=AUTH).text
    text_b = client.get(f"/artifacts/{workflow_b}/qm_output.txt", headers=AUTH).text
    assert _OUTPUT_RE.search(text_a).group(1) == _OUTPUT_RE.search(text_b).group(1)


def test_idempotency_key_dedups_launch(client):
    first = _launch(client, idempotency_key="fixed-key").json()["workflowId"]
    second = _launch(client, idempotency_key="fixed-key").json()["workflowId"]
    assert first == second


def test_force_fail_sentinel_reaches_failed_state(client):
    workflow_id = _launch(client, method="B3LYP-FORCE_FAIL").json()["workflowId"]
    for _ in range(2):
        response = client.get(f"/workflow/{workflow_id}", headers=AUTH)
    assert response.json()["workflow"]["status"] == "FAILED"
    artifact = client.get(f"/artifacts/{workflow_id}/qm_output.txt", headers=AUTH)
    assert artifact.status_code == 409


def test_force_nonconverged_sentinel(client):
    workflow_id = _launch(client, method="B3LYP-NOCONVERGE").json()["workflowId"]
    for _ in range(2):
        client.get(f"/workflow/{workflow_id}", headers=AUTH)
    artifact = client.get(f"/artifacts/{workflow_id}/qm_output.txt", headers=AUTH)
    assert artifact.status_code == 200
    assert _OUTPUT_RE.search(artifact.text).group(2) == "False"


def test_unknown_workflow_id_404(client):
    response = client.get("/workflow/does-not-exist", headers=AUTH)
    assert response.status_code == 404


def test_artifact_accepts_launcher_token_when_no_separate_store_token(client):
    workflow_id = _launch(client).json()["workflowId"]
    for _ in range(2):
        client.get(f"/workflow/{workflow_id}", headers=AUTH)
    response = client.get(f"/artifacts/{workflow_id}/qm_output.txt", headers=AUTH)
    assert response.status_code == 200
