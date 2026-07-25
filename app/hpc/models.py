"""Request/response shapes for the mocked Seqera-Tower-style launcher API.

Mirrors exactly what Chemclaw3's real HTTP client (`workflows/hpc/nextflow.py`) sends and
expects — see that module for the authoritative contract. Kept loose on the request side
(`extra="allow"`) since the mock only needs `params.smiles/method/basis_set` to compute a
deterministic result; everything else it echoes back untouched.
"""

from pydantic import BaseModel, ConfigDict, Field


class LaunchParams(BaseModel):
    """The QM parameters nested under `LaunchRequest.params`."""

    model_config = ConfigDict(extra="allow")

    smiles: str = ""
    method: str = ""
    basis_set: str = ""


class LaunchRequest(BaseModel):
    """Body of `POST /workflow/launch`."""

    model_config = ConfigDict(extra="allow")

    pipeline: str = ""
    revision: str = ""
    params: LaunchParams = Field(default_factory=LaunchParams)


class LaunchResponse(BaseModel):
    """Response of `POST /workflow/launch` — the client reads `workflowId`."""

    workflowId: str


class WorkflowStatus(BaseModel):
    """The `workflow.status` sub-object the client reads from `GET /workflow/{id}`."""

    status: str


class WorkflowStatusResponse(BaseModel):
    """Response of `GET /workflow/{id}`."""

    workflow: WorkflowStatus
