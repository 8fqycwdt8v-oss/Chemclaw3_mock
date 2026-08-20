"""Chemclaw3_mock: a single lightweight FastAPI process standing in for Chemclaw3's HPC launcher
ELN datasources and (opt-in) an Entra ID tenant during testing. Run with:

    uvicorn app.main:app --port 8090

See README.md for the full wiring guide (which CHEMCLAW_* env vars to set on a Chemclaw3
checkout to point it at this backend). The vendor MCP tool is a separate process — see
app/mcp_tools/vendor_server.py.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.eln.router import router as eln_router
from app.eln.seed import seed_all
from app.entra.router import router as entra_router
from app.hpc.router import router as hpc_router


@asynccontextmanager
async def _lifespan(_: FastAPI):
    if settings.eln_seed_on_startup:
        seed_all(reset=True)
    yield


app = FastAPI(
    title="Chemclaw3 Mock Backend",
    description="Mock HPC launcher + ELN datasources for testing Chemclaw3 without real infra.",
    lifespan=_lifespan,
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(hpc_router)
app.include_router(eln_router)
# Mounted always, refused unless MOCK_ENTRA_ENABLED — so a misconfigured lane gets a 404 naming the
# switch rather than a route that silently is not there. See app/entra/ for why it is off by default.
app.include_router(entra_router)
