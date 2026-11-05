"""A `slurmrestd`-compatible stand-in (API v0.0.40): submit, status, cancel and accounting.

Chemclaw3's `slurm_rest` compute driver talks to a site's `slurmrestd`; this answers the same four
calls so the driver and the external-job workflow can be driven end to end with no cluster. A job
runs nothing. It is pending for `MOCK_SLURM_PENDING_SECONDS`, running for
`MOCK_SLURM_RUN_SECONDS`, then ends in the outcome its submission asked for:
`MOCK_SLURM_OUTCOME` in the job's `environment` (`COMPLETED`, `FAILED`, `NODE_FAIL`, `TIMEOUT`,
`OUT_OF_MEMORY`), else `MOCK_SLURM_DEFAULT_OUTCOME`. State is derived from the clock on every
read, so a test moves a job along by moving `clock`.

When a job ends, its artifact directory `<MOCK_SLURM_ARTIFACT_DIR>/<job_id>/` holds the submitted
script and its stdout (and stderr on a failure), the way a shared scratch file system would.
Accounting reports the CPUs allocated and the elapsed seconds; their product is the job's cost.
Requests need `X-SLURM-USER-NAME` and `X-SLURM-USER-TOKEN`, the token equal to `MOCK_SLURM_TOKEN`.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings

API = "v0.0.40"

Outcome = Literal["COMPLETED", "FAILED", "NODE_FAIL", "TIMEOUT", "OUT_OF_MEMORY"]
OUTCOMES: tuple[Outcome, ...] = ("COMPLETED", "FAILED", "NODE_FAIL", "TIMEOUT", "OUT_OF_MEMORY")

#: The exit code each ending reports, as Slurm does: a timeout or node failure is a signal-killed
#: batch step, an out-of-memory kill is a SIGKILL from the cgroup.
_EXIT_CODES: dict[str, int] = {
    "COMPLETED": 0,
    "FAILED": 1,
    "NODE_FAIL": 0,
    "TIMEOUT": 0,
    "OUT_OF_MEMORY": 137,
    "CANCELLED": 0,
}

#: Seconds since the epoch. Tests replace it to move jobs through their states.
clock: Callable[[], float] = time.time

router = APIRouter()


class JobDescription(BaseModel):
    """The part of slurmrestd's `job_desc_msg` this stand-in reads; everything else is accepted."""

    model_config = ConfigDict(extra="allow")

    name: str = "job"
    environment: list[str] = Field(default_factory=list)
    current_working_directory: str | None = None
    cpus_per_task: int = Field(default=1, ge=1)
    tasks: int = Field(default=1, ge=1)


class SubmitRequest(BaseModel):
    """A `POST /slurm/v0.0.40/job/submit` body."""

    model_config = ConfigDict(extra="allow")

    script: str = Field(min_length=1)
    job: JobDescription


@dataclass
class _Job:
    job_id: int
    name: str
    script: str
    cpus: int
    outcome: Outcome
    submitted: float
    cancelled_at: float | None = None
    artifacts_written: bool = False

    @property
    def started(self) -> float:
        return self.submitted + settings.slurm_pending_seconds

    @property
    def finished(self) -> float:
        return self.started + settings.slurm_run_seconds

    def state(self, now: float) -> str:
        if self.cancelled_at is not None and self.cancelled_at < self.finished:
            return "CANCELLED"
        if now < self.started:
            return "PENDING"
        if now < self.finished:
            return "RUNNING"
        return self.outcome

    def ended_at(self, now: float) -> float | None:
        current = self.state(now)
        if current == "CANCELLED":
            return self.cancelled_at
        return self.finished if current in OUTCOMES else None

    def elapsed(self, now: float) -> int:
        end = self.ended_at(now) or now
        return max(0, int(end - self.started)) if end > self.started else 0


_jobs: dict[int, _Job] = {}
_ids = itertools.count(1001)


def reset() -> None:
    """Forget every job (tests)."""
    global _ids
    _jobs.clear()
    _ids = itertools.count(1001)


def _authenticate(user: str | None, token: str | None) -> None:
    if not user or token != settings.slurm_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "X-SLURM-USER-NAME and an X-SLURM-USER-TOKEN equal to MOCK_SLURM_TOKEN are required"
            ),
        )


def _outcome(environment: list[str]) -> Outcome:
    requested = next(
        (
            entry.split("=", 1)[1]
            for entry in environment
            if entry.startswith("MOCK_SLURM_OUTCOME=")
        ),
        settings.slurm_default_outcome,
    )
    if requested not in OUTCOMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MOCK_SLURM_OUTCOME={requested!r} is not one of {', '.join(OUTCOMES)}",
        )
    return requested  # type: ignore[return-value]


def _job(job_id: int) -> _Job:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"job {job_id} not found")
    return job


def _write_artifacts(job: _Job, now: float) -> None:
    """Materialize the job's directory once it has ended, as the batch step would have left it."""
    current = job.state(now)
    if job.artifacts_written or current in ("PENDING", "RUNNING"):
        return
    directory = settings.slurm_artifact_dir / str(job.job_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.sh").write_text(job.script, encoding="utf-8")
    (directory / f"slurm-{job.job_id}.out").write_text(
        f"mock slurm job {job.job_id} ({job.name}) ended {current}\n", encoding="utf-8"
    )
    if current != "COMPLETED":
        (directory / f"slurm-{job.job_id}.err").write_text(
            f"slurmstepd: error: job {job.job_id} ended {current}\n", encoding="utf-8"
        )
    job.artifacts_written = True


def _number(value: float | int | None) -> dict[str, Any]:
    """slurmrestd's optional-number shape."""
    if value is None:
        return {"set": False, "infinite": False, "number": 0}
    return {"set": True, "infinite": False, "number": int(value)}


def _exit_code(job: _Job, current: str) -> dict[str, Any]:
    code = _EXIT_CODES.get(current, 0)
    return {
        "status": ["SUCCESS" if current == "COMPLETED" else "ERROR"],
        "return_code": _number(code if current not in ("PENDING", "RUNNING") else None),
    }


def _envelope(**body: Any) -> dict[str, Any]:
    return {**body, "errors": [], "warnings": []}


@router.post(f"/slurm/{API}/job/submit")
def submit(
    request: SubmitRequest,
    x_slurm_user_name: str | None = Header(default=None),
    x_slurm_user_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _authenticate(x_slurm_user_name, x_slurm_user_token)
    job = _Job(
        job_id=next(_ids),
        name=request.job.name,
        script=request.script,
        cpus=request.job.cpus_per_task * request.job.tasks,
        outcome=_outcome(request.job.environment),
        submitted=clock(),
    )
    _jobs[job.job_id] = job
    return _envelope(job_id=job.job_id, step_id="batch", result={"job_id": job.job_id})


@router.get(f"/slurm/{API}/job/{{job_id}}")
def job_status(
    job_id: int,
    x_slurm_user_name: str | None = Header(default=None),
    x_slurm_user_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _authenticate(x_slurm_user_name, x_slurm_user_token)
    job, now = _job(job_id), clock()
    current = job.state(now)
    _write_artifacts(job, now)
    return _envelope(
        jobs=[
            {
                "job_id": job.job_id,
                "name": job.name,
                "job_state": [current],
                "submit_time": _number(job.submitted),
                "start_time": _number(job.started if current != "PENDING" else None),
                "end_time": _number(job.ended_at(now)),
                "exit_code": _exit_code(job, current),
                "standard_output": str(
                    settings.slurm_artifact_dir / str(job.job_id) / f"slurm-{job.job_id}.out"
                ),
            }
        ]
    )


@router.delete(f"/slurm/{API}/job/{{job_id}}")
def cancel(
    job_id: int,
    x_slurm_user_name: str | None = Header(default=None),
    x_slurm_user_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _authenticate(x_slurm_user_name, x_slurm_user_token)
    job, now = _job(job_id), clock()
    if job.state(now) in ("PENDING", "RUNNING"):
        job.cancelled_at = now
        _write_artifacts(job, now)
    return _envelope()


@router.get(f"/slurmdb/{API}/job/{{job_id}}")
def accounting(
    job_id: int,
    x_slurm_user_name: str | None = Header(default=None),
    x_slurm_user_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _authenticate(x_slurm_user_name, x_slurm_user_token)
    job, now = _job(job_id), clock()
    current, elapsed = job.state(now), job.elapsed(now)
    return _envelope(
        jobs=[
            {
                "job_id": job.job_id,
                "name": job.name,
                "state": {"current": [current], "reason": "None"},
                "time": {
                    "submission": int(job.submitted),
                    "start": int(job.started) if current != "PENDING" else 0,
                    "end": int(job.ended_at(now) or 0),
                    "elapsed": elapsed,
                },
                "exit_code": _exit_code(job, current),
                "tres": {"allocated": [{"type": "cpu", "count": job.cpus}]},
            }
        ]
    )
