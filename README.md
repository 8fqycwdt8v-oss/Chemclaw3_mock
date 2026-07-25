# Chemclaw3_mock

A lightweight FastAPI mock/test backend for [Chemclaw3](https://github.com/8fqycwdt8v-oss/Chemclaw3):
a mocked HPC/Nextflow launcher, two ELN datasources (free-text and structured/ORD), and an
example HTTP-transport MCP tool. Everything is deterministic, CPU-light, and runs with no real
compute, no HPC cluster, no database, and no network access — meant for a plain dev/text
environment.

Every wire shape here was verified against Chemclaw3's actual source (`workflows/hpc/nextflow.py`,
`eln/json_adapter.py`, `eln/ord_adapter.py`), and the two ELN fixture sets were round-tripped
through Chemclaw3's real, unmodified adapter code with zero mapping errors.

## What's here

| Component | What it mocks | Where |
|---|---|---|
| HPC launcher | Seqera-Tower-style REST API (`CHEMCLAW_HPC_LAUNCH_INTERFACE=nextflow`) | `app/hpc/` |
| ELN — free text | A JSON-exporting ELN, USPTO-style patent procedures (`eln-json` source) | `app/eln/fixtures_data.py` (`uspto_style_records`) |
| ELN — structured | Native Open Reaction Database JSON exports (`eln-ord` source) | `app/eln/fixtures_data.py` (`ord_style_records`) |
| MCP tool | A vendor building-block search/pricing tool, HTTP transport | `app/mcp_tools/vendor_server.py` |

## Install & run

```bash
pip install -e .
uvicorn app.main:app --port 8090          # HPC launcher + ELN datasource endpoints
python -m app.mcp_tools.vendor_server      # separate process, MCP tool over HTTP, port 8091
```

On startup, the main app seeds ~25 free-text and ~24 structured reaction fixtures as individual
JSON files into `MOCK_ELN_EXPORT_DIR` / `MOCK_ORD_EXPORT_DIR` (default `./data/eln/exports` and
`./data/eln/exports/ord`). **Point Chemclaw3's own `CHEMCLAW_ELN_EXPORT_DIR` /
`CHEMCLAW_ORD_EXPORT_DIR` at those same paths** — Chemclaw3 reads ELN data as flat files off
disk, not over HTTP (see "How the ELN datasources actually connect" below).

## Wiring a Chemclaw3 checkout to this backend

Add to Chemclaw3's `.env` (or export directly):

```bash
# HPC launcher — real HTTP code path against this mock instead of the built-in in-process mock.
CHEMCLAW_HPC_LAUNCH_INTERFACE=nextflow
CHEMCLAW_HPC_API_BASE_URL=http://localhost:8090
CHEMCLAW_HPC_API_TOKEN=mock-hpc-token          # must match MOCK_HPC_API_TOKEN below
CHEMCLAW_HPC_ARTIFACT_STORE_URL=http://localhost:8090/artifacts
CHEMCLAW_HPC_PIPELINE_NAME=qm-pipeline
CHEMCLAW_HPC_PIPELINE_VERSION=mock-1

# ELN datasources — file-based; point these at the SAME paths this mock seeds into.
CHEMCLAW_DATA_SOURCES=graph,eln-json,eln-ord
CHEMCLAW_ELN_EXPORT_DIR=/absolute/path/to/Chemclaw3_mock/data/eln/exports
CHEMCLAW_ORD_EXPORT_DIR=/absolute/path/to/Chemclaw3_mock/data/eln/exports/ord

# MCP tool over HTTP transport.
CHEMCLAW_MCP_SERVERS=[{"transport":"http","name":"mock-vendor","url":"http://localhost:8091/mcp","allowed_tools":["search_building_blocks","get_price"]}]
```

And on this repo's side, set `MOCK_ELN_EXPORT_DIR` / `MOCK_ORD_EXPORT_DIR` to the exact same
absolute paths before starting `uvicorn`, e.g.:

```bash
export MOCK_ELN_EXPORT_DIR=/absolute/path/to/Chemclaw3_mock/data/eln/exports
export MOCK_ORD_EXPORT_DIR=/absolute/path/to/Chemclaw3_mock/data/eln/exports/ord
export MOCK_HPC_API_TOKEN=mock-hpc-token
uvicorn app.main:app --port 8090
```

## How the HPC mock behaves

Implements exactly the three calls Chemclaw3's real launcher client makes
(`workflows/hpc/nextflow.py`):

- `POST /workflow/launch` — Bearer-auth checked, `Idempotency-Key` deduped (a retried launch
  returns the same `workflowId` instead of double-submitting). Returns `{"workflowId": "..."}`.
- `GET /workflow/{id}` — returns `{"workflow": {"status": "..."}}`. The run advances one state
  per poll (`SUBMITTED`→`RUNNING`→`SUCCEEDED`), reaching a terminal state in
  `MOCK_HPC_POLLS_UNTIL_DONE` polls (default 2) — no real wall-clock wait, so Chemclaw3's
  heartbeat-poll loop is genuinely exercised without slowing tests down.
- `GET /artifacts/{id}/qm_output.txt` — returns `energy=<float> converged=<bool>` text matching
  Chemclaw3's `parse_qm_output` regex exactly. 409 until the run reaches `SUCCEEDED`.

The synthetic energy is a deterministic hash of `(smiles, method, basis_set)` — same inputs
always give the same energy, no randomness, no real QM.

**Testing error paths** — no config needed, just send a `method` string containing one of these
substrings:
- `FORCE_FAIL` — the run terminates `FAILED` (tests Chemclaw3's non-retryable failure handling).
- `NOCONVERGE` — the run `SUCCEEDED`s but the artifact reports `converged=False`.

Auth is enforced by default (`MOCK_HPC_ENFORCE_AUTH=true`): a missing/wrong bearer token gets a
401. Set `MOCK_HPC_ENFORCE_AUTH=false` to skip that check entirely.

## How the ELN datasources actually connect

Chemclaw3's ELN sync (`eln/json_adapter.py`, `eln/ord_adapter.py`) reads `*.json` files
directly from `CHEMCLAW_ELN_EXPORT_DIR` / `CHEMCLAW_ORD_EXPORT_DIR` — **there is no HTTP call
for ELN data**. So this mock's real integration point is the files it writes on startup, not an
API. The HTTP router (`GET/POST /eln/json/entries`, `GET/POST /eln/ord/entries`,
`POST /eln/reset`) is a control surface for testing:

- `GET /eln/{json,ord}/entries` — list what's currently seeded.
- `POST /eln/{json,ord}/entries` — append one new entry stamped after every existing one, to
  simulate live ELN activity and exercise Chemclaw3's `since`-cursor incremental sync.
- `POST /eln/reset` — clear and reseed the original fixture set.

### Free-text source (`eln-json`, USPTO-style)

~25 records covering 12 real named reactions (Suzuki, Buchwald-Hartwig, amide coupling, Grignard,
Friedel-Crafts, Wittig, SNAr, Sonogashira, reductive amination, Fischer esterification, epoxide
opening, Boc deprotection — real SMILES throughout). About half rely on Chemclaw3's regex-based
temperature/time recovery from patent-style procedure prose ("...stirred at 82 °C for 4.0 h...");
the rest carry structured `temperature_c`/`time_h` fields directly. Includes one entry with an
impurity profile and one explicit `outcome: failure` record with a `failure_reason`.

### Structured source (`eln-ord`, Open Reaction Database)

~24 records in native ORD `Reaction` JSON shape: component-linked `inputs` (with
`additionOrder`/`additionTime`), `conditions.temperature`, `outcomes[].products[].measurements`
(YIELD/PURITY), and a `workups[]` sequence (wash + filtration) — so Chemclaw3's `OrdJsonAdapter`
produces genuinely step-linked procedures, not prose-segmented guesses.

## MCP vendor tool

`python -m app.mcp_tools.vendor_server` runs a FastMCP server over Streamable HTTP (port 8091 by
default) exposing:
- `search_building_blocks(query)` — substring match over a ~20-entry mock catalog by name or
  SMILES (several SMILES overlap the ELN fixtures above, e.g. 4-bromoanisole, aniline, morpholine).
- `get_price(catalog_id)` — full pricing/availability detail for one listing.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Covers the HPC launch→poll→artifact lifecycle (including auth failures, idempotency dedup, and
both error sentinels) and the ELN list/append/reset endpoints. The ELN fixtures themselves were
additionally verified against Chemclaw3's real `JsonExportAdapter`/`OrdJsonAdapter` classes
directly (not just shape assertions here) — both parsed all seeded entries with zero mapping
errors.

## Configuration reference (this backend's own env vars)

| Variable | Default | Meaning |
|---|---|---|
| `MOCK_HPC_API_TOKEN` | `mock-hpc-token` | Expected bearer token for `/workflow/*` |
| `MOCK_HPC_ARTIFACT_STORE_TOKEN` | (empty) | Separate artifact-store token; falls back to the launcher token when unset |
| `MOCK_HPC_ENFORCE_AUTH` | `true` | Set `false` to accept any/no Authorization header |
| `MOCK_HPC_POLLS_UNTIL_DONE` | `2` | How many `GET /workflow/{id}` calls before a run reaches its terminal state |
| `MOCK_HPC_UNKNOWN_STATUS_EVERY_N` | `0` (off) | Every Nth poll before completion returns launcher status `UNKNOWN` instead of `RUNNING` |
| `MOCK_ELN_EXPORT_DIR` | `./data/eln/exports` | Where free-text fixtures are seeded |
| `MOCK_ORD_EXPORT_DIR` | `./data/eln/exports/ord` | Where ORD fixtures are seeded |
| `MOCK_ELN_SEED_ON_STARTUP` | `true` | Seed (and clear) both directories when the app starts |
| `MOCK_MCP_VENDOR_HOST` / `MOCK_MCP_VENDOR_PORT` | `0.0.0.0` / `8091` | Bind address for the vendor MCP server |
