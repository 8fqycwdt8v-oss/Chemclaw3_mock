"""In-memory job store for the mocked HPC launcher: deterministic, no real compute.

A job's synthetic QM result is derived purely from `hash(smiles, method, basis_set)` — no xTB,
no real quantum chemistry, no meaningful wall-clock delay — so this runs anywhere, instantly,
and reproducibly (the same molecule always yields the same energy). The state machine
(SUBMITTED -> RUNNING -> SUCCEEDED/FAILED) advances one step per poll so Chemclaw3's real
polling loop (`workflows/activities._poll_nextflow`) is genuinely exercised without slow
wall-clock waits.

Two sentinels let a caller test error paths deterministically without any extra config:
  - a `method` containing "FORCE_FAIL" (case-insensitive) makes the run terminate FAILED.
  - a `method` containing "NOCONVERGE" (case-insensitive) makes it SUCCEED with converged=False.
"""

import hashlib
import threading
from dataclasses import dataclass, field

from app.config import settings

_ENERGY_MIN_HARTREE = -2000.0
_ENERGY_MAX_HARTREE = -50.0


@dataclass
class Job:
    workflow_id: str
    smiles: str
    method: str
    basis_set: str
    poll_count: int = 0
    idempotency_key: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def force_fail(self) -> bool:
        return "FORCE_FAIL" in self.method.upper()

    @property
    def force_nonconverged(self) -> bool:
        return "NOCONVERGE" in self.method.upper()

    def energy_hartree(self) -> float:
        """Deterministic pseudo-energy from a stable hash of the job's chemistry inputs."""
        digest = hashlib.sha256(f"{self.smiles}|{self.method}|{self.basis_set}".encode()).digest()
        fraction = int.from_bytes(digest[:8], "big") / float(2**64)
        return _ENERGY_MIN_HARTREE + fraction * (_ENERGY_MAX_HARTREE - _ENERGY_MIN_HARTREE)

    def status(self) -> str:
        """The launcher status string for the current poll count (advances the state machine)."""
        polls_until_done = max(settings.hpc_polls_until_done, 1)
        if self.poll_count == 0:
            return "SUBMITTED"
        every_n = settings.hpc_unknown_status_every_n_polls
        if every_n > 0 and self.poll_count % every_n == 0 and self.poll_count < polls_until_done:
            return "UNKNOWN"
        if self.poll_count < polls_until_done:
            return "RUNNING"
        return "FAILED" if self.force_fail else "SUCCEEDED"

    def qm_output_text(self) -> str:
        """The raw artifact text, matching Chemclaw3's `energy=… converged=…` regex exactly."""
        converged = not self.force_nonconverged
        return f"energy={self.energy_hartree():.6f} converged={converged}"


class JobStore:
    """Thread-safe in-memory registry of launched jobs, keyed by workflow id and idempotency key."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._by_idempotency_key: dict[str, str] = {}
        self._lock = threading.Lock()
        self._sequence = 0

    def launch(
        self, *, smiles: str, method: str, basis_set: str, idempotency_key: str | None
    ) -> Job:
        """Create a new job, or return the existing one for a reused idempotency key."""
        with self._lock:
            if idempotency_key and idempotency_key in self._by_idempotency_key:
                return self._jobs[self._by_idempotency_key[idempotency_key]]
            self._sequence += 1
            workflow_id = f"mock-run-{self._sequence:06d}"
            job = Job(
                workflow_id=workflow_id,
                smiles=smiles,
                method=method,
                basis_set=basis_set,
                idempotency_key=idempotency_key,
            )
            self._jobs[workflow_id] = job
            if idempotency_key:
                self._by_idempotency_key[idempotency_key] = workflow_id
            return job

    def get(self, workflow_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(workflow_id)

    def poll(self, workflow_id: str) -> Job | None:
        """Look up a job and advance its poll count by one (the state machine's clock)."""
        with self._lock:
            job = self._jobs.get(workflow_id)
            if job is None:
                return None
            job.poll_count += 1
            return job

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._by_idempotency_key.clear()
            self._sequence = 0


job_store = JobStore()
