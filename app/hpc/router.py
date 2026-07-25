"""The mocked Seqera-Tower-style launcher, matching `workflows/hpc/nextflow.py` byte-for-byte:

  POST /workflow/launch                          -> {"workflowId": "..."}
  GET  /workflow/{scheduler_job_id}               -> {"workflow": {"status": "..."}}
  GET  /artifacts/{scheduler_job_id}/qm_output.txt -> "energy=... converged=..."

Point Chemclaw3 at this router with `CHEMCLAW_HPC_API_BASE_URL=http://<host>:<port>` and
`CHEMCLAW_HPC_ARTIFACT_STORE_URL=http://<host>:<port>/artifacts` (see README.md).
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.hpc.auth import require_artifact_auth, require_launcher_auth
from app.hpc.models import LaunchRequest, LaunchResponse, WorkflowStatus, WorkflowStatusResponse
from app.hpc.store import job_store

router = APIRouter()


@router.post(
    "/workflow/launch", response_model=LaunchResponse, dependencies=[Depends(require_launcher_auth)]
)
def launch(body: LaunchRequest, idempotency_key: str | None = Header(default=None)) -> LaunchResponse:
    job = job_store.launch(
        smiles=body.params.smiles,
        method=body.params.method,
        basis_set=body.params.basis_set,
        idempotency_key=idempotency_key,
    )
    return LaunchResponse(workflowId=job.workflow_id)


@router.get(
    "/workflow/{scheduler_job_id}",
    response_model=WorkflowStatusResponse,
    dependencies=[Depends(require_launcher_auth)],
)
def poll(scheduler_job_id: str) -> WorkflowStatusResponse:
    job = job_store.poll(scheduler_job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown workflow id")
    return WorkflowStatusResponse(workflow=WorkflowStatus(status=job.status()))


@router.get("/artifacts/{scheduler_job_id}/qm_output.txt", dependencies=[Depends(require_artifact_auth)])
def artifact(scheduler_job_id: str) -> Response:
    job = job_store.get(scheduler_job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown workflow id")
    if job.status() != "SUCCEEDED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run is {job.status()}, no artifact yet",
        )
    return Response(content=job.qm_output_text(), media_type="text/plain")


@router.post("/_mock/reset", include_in_schema=False)
def reset() -> dict[str, str]:
    """Test-only helper: clear all launched jobs (not part of the real launcher's contract)."""
    job_store.reset()
    return {"status": "reset"}
