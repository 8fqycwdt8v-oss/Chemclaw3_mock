"""The slurmrestd stand-in: a job's states follow the clock, and it ends as its submission asked."""

import pytest

from app.config import settings
from app.slurm import router as slurm

AUTH = {"X-SLURM-USER-NAME": "chemist", "X-SLURM-USER-TOKEN": "mock-slurm-token"}
API = "/slurm/v0.0.40"


@pytest.fixture
def at(monkeypatch, tmp_path):
    """A settable clock, an empty job table and a private artifact directory."""
    slurm.reset()
    monkeypatch.setattr(settings, "slurm_pending_seconds", 10.0)
    monkeypatch.setattr(settings, "slurm_run_seconds", 100.0)
    monkeypatch.setattr(settings, "slurm_artifact_dir", tmp_path / "slurm")
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(slurm, "clock", lambda: now["t"])

    def move_to(seconds_after_start: float) -> None:
        now["t"] = 1_000_000.0 + seconds_after_start

    yield move_to
    slurm.reset()


def _submit(client, *environment: str, cpus: int = 1) -> int:
    response = client.post(
        f"{API}/job/submit",
        headers=AUTH,
        json={"script": "#!/bin/bash\necho hi\n",
              "job": {"name": "dft", "environment": list(environment), "cpus_per_task": cpus}},
    )
    assert response.status_code == 200, response.text
    return response.json()["job_id"]


def _state(client, job_id: int) -> str:
    return client.get(f"{API}/job/{job_id}", headers=AUTH).json()["jobs"][0]["job_state"][0]


def test_a_job_is_pending_then_running_then_completed(client, at):
    job_id = _submit(client)
    assert _state(client, job_id) == "PENDING"
    at(50)
    assert _state(client, job_id) == "RUNNING"
    at(111)
    assert _state(client, job_id) == "COMPLETED"


@pytest.mark.parametrize("outcome", ["FAILED", "NODE_FAIL", "TIMEOUT", "OUT_OF_MEMORY"])
def test_a_job_ends_in_the_outcome_its_submission_asked_for(client, at, outcome):
    job_id = _submit(client, f"MOCK_SLURM_OUTCOME={outcome}")
    at(111)
    job = client.get(f"{API}/job/{job_id}", headers=AUTH).json()["jobs"][0]
    assert job["job_state"] == [outcome]
    assert job["exit_code"]["status"] == ["ERROR"]


def test_an_unknown_outcome_is_refused_at_submission(client, at):
    response = client.post(
        f"{API}/job/submit",
        headers=AUTH,
        json={"script": "x", "job": {"environment": ["MOCK_SLURM_OUTCOME=EXPLODED"]}},
    )
    assert response.status_code == 400


def test_a_cancelled_job_stays_cancelled_after_it_would_have_finished(client, at):
    job_id = _submit(client)
    at(50)
    assert client.delete(f"{API}/job/{job_id}", headers=AUTH).status_code == 200
    at(500)
    assert _state(client, job_id) == "CANCELLED"


def test_accounting_reports_the_cpus_and_the_seconds_the_job_ran(client, at):
    job_id = _submit(client, cpus=8)
    at(111)
    job = client.get(f"/slurmdb/v0.0.40/job/{job_id}", headers=AUTH).json()["jobs"][0]
    assert job["state"]["current"] == ["COMPLETED"]
    assert job["time"]["elapsed"] == 100
    assert job["tres"]["allocated"] == [{"type": "cpu", "count": 8}]


def test_an_ended_job_leaves_its_script_and_output_in_its_directory(client, at):
    ok = _submit(client)
    failed = _submit(client, "MOCK_SLURM_OUTCOME=FAILED")
    at(111)
    _state(client, ok), _state(client, failed)
    directory = settings.slurm_artifact_dir
    assert (directory / str(ok) / "job.sh").read_text() == "#!/bin/bash\necho hi\n"
    assert "COMPLETED" in (directory / str(ok) / f"slurm-{ok}.out").read_text()
    assert not (directory / str(ok) / f"slurm-{ok}.err").exists()
    assert "FAILED" in (directory / str(failed) / f"slurm-{failed}.err").read_text()


def test_a_running_job_has_no_directory_yet(client, at):
    job_id = _submit(client)
    at(50)
    _state(client, job_id)
    assert not (settings.slurm_artifact_dir / str(job_id)).exists()


def test_every_call_needs_the_user_and_the_token(client, at):
    assert client.post(f"{API}/job/submit", json={"script": "x", "job": {}}).status_code == 401
    wrong = {**AUTH, "X-SLURM-USER-TOKEN": "nope"}
    assert client.get(f"{API}/job/1001", headers=wrong).status_code == 401


def test_an_unknown_job_is_not_found(client, at):
    assert client.get(f"{API}/job/42", headers=AUTH).status_code == 404
