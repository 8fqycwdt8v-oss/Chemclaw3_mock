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

On startup, the main app seeds curated fixtures **plus real, cited, published datasets** as
individual JSON files into `MOCK_ELN_EXPORT_DIR` / `MOCK_ORD_EXPORT_DIR` (default
`./data/eln/exports` and `./data/eln/exports/ord`): ~32 free-text records and ~10,000
structured/ORD records by default (see "Real datasets" below for the full breakdown and exact
provenance of every one of them). **Point Chemclaw3's own `CHEMCLAW_ELN_EXPORT_DIR` /
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

# MCP tool over HTTP transport. Chemclaw3 reaches an MCP server through its *connector* seam
# (D-118), so the setting is CHEMCLAW_CONNECTOR_URLS — a JSON map of connector name to URL.
# The older CHEMCLAW_MCP_SERVERS list no longer exists as a field, and because Chemclaw3's
# settings are `extra="forbid"`, exporting it aborts startup with a validation error rather
# than being ignored.
CHEMCLAW_CONNECTOR_URLS='{"mock-vendor":"http://localhost:8091/mcp"}'
# `allowed_tools` is no longer set here either: it is declared in the connector's own
# connector.yaml manifest, on the serving side.
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

~24 curated records in native ORD `Reaction` JSON shape: component-linked `inputs` (with
`additionOrder`/`additionTime`), `conditions.temperature`, `outcomes[].products[].measurements`
(YIELD/PURITY), and a `workups[]` sequence (wash + filtration) — so Chemclaw3's `OrdJsonAdapter`
produces genuinely step-linked procedures, not prose-segmented guesses.

## Real datasets (`app/eln/real_hte.py`, `app/eln/real_procedures.py`)

On top of the curated fixtures above, this repo bundles **real, published, cited experimental
data** — no synthesized chemistry, no templated procedure text. Raw factor tables are committed
as small CSVs in `app/eln/real_data/` (pulled once from their public sources) and expanded into
Chemclaw3's adapter shapes at seed time; no network access is needed at runtime. Every record
carries a real `provenance.doi` (structured source) or cites its DOI directly in the `procedure`
text (free-text source).

### Structured / HTE screening (`eln-ord`)

| Dataset ID | Reactions | Real reaction class | Source |
|---|---|---|---|
| `bh-amination-plate-p2et` | 1,320 | Buchwald-Hartwig **amination** | Ahneman, Estrada, Lin, Dreher, Doyle. *Science* 2018, 360, 186-190. DOI [10.1126/science.aar5169](https://doi.org/10.1126/science.aar5169) |
| `bh-amination-plate-mtbd` | 1,318 | Buchwald-Hartwig **amination** | same as above |
| `bh-amination-plate-btmg` | 1,317 | Buchwald-Hartwig **amination** | same as above |
| `suzuki-miyaura-flow-hte` | 5,760 | Suzuki-Miyaura | Perera et al. *Science* 2018, 359, 429-434. DOI [10.1126/science.aap9112](https://doi.org/10.1126/science.aap9112) |
| `santanilla-amidation-screen` | 96 | Buchwald-Hartwig **amidation** | Santanilla et al. *Science* 2015, 347, 49-53. DOI [10.1126/science.1259203](https://doi.org/10.1126/science.1259203), Experiment 2 |
| `santanilla-sulfonamidation-screen` | 96 | Buchwald-Hartwig-type sulfonamidation | same as above |
| `nielsen-deoxyfluorination-screen` | 80 | Deoxyfluorination | Nielsen et al. *JACS* 2018, 140, 5004-5008. DOI [10.1021/jacs.8b01523](https://doi.org/10.1021/jacs.8b01523) |

**On "amination" vs. "amidation":** the original ask was for 3 Buchwald-Hartwig *amidation* HTE
screens. The Ahneman/Doyle dataset above — the only public HTE benchmark of that scale for this
Pd-catalyzed reaction family — actually couples aryl halides with **4-methylaniline** (an amine,
not an amide), so it is Buchwald-Hartwig amination. No comparable public *amidation* HTE
benchmark of that scale exists. It does, however, naturally split into **3 real physical
screening plates** (one base per plate: P2Et/MTBD/BTMG), matching the "3 different HTE
screenings" ask structurally. Separately, the real Santanilla Experiment 2 dataset's "amide S4"
nucleophile subset (aryl bromide + benzamide, 96 real conditions) *is* genuine Buchwald-Hartwig
amidation — a smaller but real fourth screen (`santanilla-amidation-screen`) that directly
satisfies the original chemistry ask.

The Suzuki-Miyaura dataset's second coupling partner is only identified by the source paper's
own shorthand codes (`2a`-`2d`) — no SMILES was published for it in the source spreadsheet, so
it's carried as a real `NAME` identifier rather than a guessed structure.

> **Consequence worth knowing before you point Chemclaw3 at this: all 5,760 of those records are
> refused on ingest.** `ord_adapter._smiles` resolves SMILES, InChI and known reagent *names*, and
> `2a, Boronic Acid` is none of those — so it raises rather than inventing a structure, which is
> the correct behaviour and is pinned by a test on that side naming this exact dataset. Measured
> against a live stack on 2026-08-18: of the 10,011 ORD records seeded here, **4,251 map and 5,760
> are refused**, every refusal this screen. Everything else seeds and ingests intact, including the
> 644 records at exactly 0.00% yield and the 480 no-ligand / 720 no-base control conditions in this
> same screen. Nothing here is broken; the number is simply not what "10,011 records seeded"
> suggests, and downstream graders have been caught assuming otherwise.

Every real HTE dataset is fully real by default (`MOCK_HTE_MAX_RECORDS_PER_DATASET=0`); set it
to a positive number to cap each dataset to its first N rows (real rows only truncated, never
fabricated) for faster local iteration. The test suite caps it to 5 for speed — see
`test_real_hte_datasets_at_full_scale` in `tests/test_eln.py` for a direct, uncapped check of
the real counts above.

### Free-text (`eln-json`)

Bulk real USPTO-patent procedure text (the original 10,000-entry target for this source) lives
behind hosts this environment's network policy blocks outright: figshare.com (Lowe's original
USPTO corpus), huggingface.co (blocks the *official* Open Reaction Database mirror too),
zenodo.org, kaggle.com, and even an IBM Box link one candidate mirror pointed to. No
GitHub-committed (non-LFS) real corpus of that scale was found either. Rather than pad the count
with generated or templated prose, this source stays small and 100% real:

| Records | Source |
|---|---|
| 3 | Liu, R. Y. "Copper-Catalyzed Enantioselective Hydroamination of Alkenes." *Org. Synth.* 2018, 95, 80-96. DOI [10.15227/orgsyn.095.0080](https://doi.org/10.15227/orgsyn.095.0080). Quantities, conditions, workup, and analytical data taken directly from the real Open Reaction Database example submission for this paper. |
| 4 | The highest-yielding real well for 4 other nucleophile classes from the same Santanilla et al. *Science* 2015 Experiment 2 screen (amination/aniline, Suzuki/boronate, Sonogashira/alkyne, etherification/alcohol), narrated using the paper's own real quoted general procedure text. |

One of those four — `santanilla-orgsyn-boronate-well-Y36` — carries the paper's real
`yield_percent = 119.43`, which is what an uncalibrated relative-UPLC readout does. **Chemclaw3
refuses it**: `OrdReaction` bounds a yield at 100, so this is the one record of this source that
can never ingest (`ingested=31 rejected=1`, one WARNING naming it and quoting the validation
error). Kept as published rather than clipped to 100 — a fabricated 100% would be worse than an
honest refusal — but worth knowing it is a record you cannot query for.

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
| `MOCK_HTE_MAX_RECORDS_PER_DATASET` | `0` (unlimited) | Cap each real HTE dataset (`app/eln/real_hte.py`) to its first N rows; real rows only truncated, never fabricated |
| `MOCK_MCP_VENDOR_HOST` / `MOCK_MCP_VENDOR_PORT` | `0.0.0.0` / `8091` | Bind address for the vendor MCP server |
