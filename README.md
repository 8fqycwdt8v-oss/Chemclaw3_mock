# Chemclaw3_mock

A lightweight FastAPI mock/test backend for [Chemclaw3](https://github.com/8fqycwdt8v-oss/Chemclaw3):
two ELN datasources (free-text and structured/ORD), a stand-in Entra tenant, and an
example HTTP-transport MCP tool. Everything is deterministic, CPU-light, and runs with no real
compute, no database, and no network access — meant for a plain dev/text environment.

(It also carried a mocked HPC/Nextflow launcher until Chemclaw3 removed that tier entirely —
`D-2026-08-26-semiempirical-is-the-whole-tier` there. Nothing is left to stand in for.)

Every wire shape here was verified against Chemclaw3's actual source
(`eln/json_adapter.py`, `eln/ord_adapter.py`), and the two ELN fixture sets were round-tripped
through Chemclaw3's real, unmodified adapter code with zero mapping errors.

## What's here

| Component | What it mocks | Where |
|---|---|---|
| ELN — free text | A JSON-exporting ELN, USPTO-style patent procedures (`eln-json` source) | `app/eln/fixtures_data.py` (`uspto_style_records`) |
| ELN — structured | Native Open Reaction Database JSON exports (`eln-ord` source) | `app/eln/fixtures_data.py` (`ord_style_records`) |
| MCP tool | A vendor building-block search/pricing tool, HTTP transport | `app/mcp_tools/vendor_server.py` |
| Entra ID | A tenant: publishes signing keys, mints tokens Chemclaw3 accepts (**opt-in**) | `app/entra/` |

## Install & run

```bash
pip install -e .
uvicorn app.main:app --port 8090          # ELN datasource + Entra endpoints
python -m app.mcp_tools.vendor_server      # separate process, MCP tool over HTTP, port 8091
```

On startup, the main app seeds curated fixtures **plus real, cited, published datasets** as
individual JSON files into `MOCK_ELN_EXPORT_DIR` / `MOCK_ORD_EXPORT_DIR` (default
`./data/eln/exports` and `./data/eln/exports/ord`): ~32 free-text records and ~10,000
structured/ORD records by default (see "Real datasets" below for the full breakdown and exact
provenance of every one of them). **Point Chemclaw3's own `CHEMCLAW_ELN_EXPORT_DIR` /
`CHEMCLAW_ORD_EXPORT_DIR` at those same paths** — Chemclaw3 reads ELN data as flat files off
disk, not over HTTP (see "How the ELN datasources actually connect" below).

### As a container (one image, two processes)

`Containerfile` builds one image for both processes. The command picks which one runs, and it
runs the same `start.sh` / `start-mcp.sh` as a checkout does. The image keeps the checkout's
layout (`/app/app`, `/app/.venv`), so the scripts' `.venv` path resolves unchanged:

```bash
docker build -f Containerfile -t chemclaw/mock:kind .
docker run --rm -p 8090:8090 chemclaw/mock:kind                    # backend: ELN/ORD + Entra, :8090
docker run --rm -p 8091:8091 chemclaw/mock:kind ./start-mcp.sh     # vendor MCP server, :8091
```

The backend seeds `MOCK_ELN_EXPORT_DIR` / `MOCK_ORD_EXPORT_DIR` on start, the same as it does
from a checkout. Both default to `/app/data/eln/exports[/ord]` in the image. To share them with
Chemclaw3, mount one volume into both containers and set both sides' variables to paths on it.
The image runs as UID 1001 in group 0, and anything it writes is group-0 writable, so an arbitrary
UID (OpenShift's restricted SCC) works too. Its `HEALTHCHECK` asks whichever process is running:
the backend's `/healthz`, or the vendor's `/mcp` transport (any HTTP status counts, because the
vendor has no health route). The base is pinned by digest. The Python dependencies are resolved at
build time, because this repository has no lockfile (see "The dependency audit" below). The
resolved set is written to `/app/requirements.lock.txt` in the image.

## The stand-in Entra tenant

Chemclaw3's front door validates every request's bearer token against a tenant's JWKS — RS256
signature, audience, issuer. All of that is testable without Microsoft, because a tenant, *to a
resource server*, is a JWKS document and an issuer string. Until this existed nothing in the
four-repo stack could run with `CHEMCLAW_ENTRA_REQUIRED=true`: the live lane pinned it false, the
UI e2e ran `AUTH_MODE=dev`, and the enforced path every real deployment runs was covered by unit
tests alone.

**It is off by default and should stay off anywhere that matters.** The mint endpoint takes no
client authentication and issues a token for whatever identity and roles are asked for — reachable
from somewhere real, it forges credentials against every resource server that trusts this issuer.

```bash
MOCK_ENTRA_ENABLED=true uvicorn app.main:app --port 8090
```

Point Chemclaw3 at it:

| Chemclaw3 setting | Value |
| --- | --- |
| `CHEMCLAW_ENTRA_REQUIRED` | `true` |
| `CHEMCLAW_ENTRA_ISSUER` | `http://127.0.0.1:8090/entra/mock-tenant/v2.0` |
| `CHEMCLAW_ENTRA_JWKS_URL` | `http://127.0.0.1:8090/entra/mock-tenant/discovery/v2.0/keys` |
| `CHEMCLAW_ENTRA_AUDIENCE` | `api://chemclaw` |

The issuer and the JWKS URL are both set because Chemclaw3 derives them independently — an issuer
alone cannot resolve a keys endpoint — and its own `MOCK_ENTRA_ISSUER` / `MOCK_ENTRA_AUDIENCE` must
match the two it is told.

Then mint whatever identity the test needs:

```bash
curl -s localhost:8090/entra/mock-tenant/oauth2/v2.0/token \
  -H 'content-type: application/json' \
  -d '{"oid":"u-alice","upn":"alice@corp.example","roles":["process-chemist"]}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
```

`roles` is what Chemclaw3 gates expensive jobs, write tools and the reviewer routes on, so this is
how a lane drives an entitled chemist and an unentitled one through the same code path.

### Minting tokens that should be refused

Half of what a lane needs to prove about authentication is what gets turned away, so every way to
be invalid is one field on the same request rather than a separate endpoint:

| Field | Mints | Refused by |
| --- | --- | --- |
| `"audience": "api://someone-else"` | a token for another resource | the confused-deputy guard |
| `"issuer": "https://attacker.test/v2.0"` | a token from another issuer | the issuer check |
| `"expires_in": -60` | an already-expired token | the expiry check |
| `"omit_expiry": true` | a token with no `exp` at all | `options={"require": ["exp"]}` |
| `"unpublished_key": true` | a forgery signed by a key this JWKS never published | the signature |

The last one is why `app/entra/keys.py` holds two keys and publishes one: a mock that can only mint
valid tokens cannot ask whether forgeries are rejected. `tests/test_entra.py` asserts each of these
is refused *for its own reason* — the class of error, not merely that one was raised.

### Minting a token that is perfectly valid and still carries no groups

`"group_overage": true` is the odd one out: it is not a way to be invalid. Past roughly 150
directory memberships, real Entra stops putting `groups` in the token and emits `_claim_names` /
`_claim_sources` pointing at a Graph endpoint instead — the token is entirely valid and the group
entitlements are simply not in it. A backend has to tell that apart from a user who is in no
groups, because reading it as the latter quietly denies exactly the users with the *most* access,
and Chemclaw3 does (`api/auth.py::_principal_from_claims` logs it and counts
`chemclaw_group_claim_overage_total`). That branch was unit-tested there and reachable from no
end-to-end lane, because this tenant could not mint the shape.

```bash
curl -s localhost:8090/entra/mock-tenant/oauth2/v2.0/token \
  -H 'content-type: application/json' \
  -d '{"oid":"u-alice","roles":["process-chemist"],"group_overage":true}'
```

`groups` is *replaced*, not accompanied — a token carrying both would take neither path, and the
substitution is what the overage is. Measured against Chemclaw3's real `validate_token` over a
socket, with its own `PyJWKClient` fetching this JWKS: the token validates, `roles` survives,
`chemclaw_group_claim_overage_total` goes 0 → 1 and the WARNING names the `oid`.

### Two shapes that are the real thing's, whether or not anything checks them

**`nbf`.** Every minted token carries one, equal to `iat`, because every token real Entra issues
does. Nothing on the reading side forces it — Chemclaw3 requires only `exp` — which is the reason
it is pinned by a test here rather than left to that side: every green lane run is evidence about
*this* token, so a claim missing only because no validator happens to demand it is a difference
nobody would ever be told about.

**The JWK's `alg`, which is not the defect it looks like.** Real Entra's JWKS entries carry no
`alg` (they carry `x5t`/`x5c`/`issuer`); `app/entra/keys.py` publishes `"alg": "RS256"`. Measured
under PyJWT 2.13, which is what Chemclaw3 validates with: `PyJWK` infers RS256 from `kty` and both
documents parse identically, so this is cosmetic and is left alone rather than churned.

**The v1-vs-v2 issuer mismatch is drivable today, and deliberately not a feature.**
`sts.windows.net/{tid}` against `login.microsoftonline.com/{tid}/v2.0` is the commonest real-tenant
misconfiguration, and reproducing it needs no code here: Chemclaw3 derives the expected issuer from
`CHEMCLAW_ENTRA_ISSUER` alone, so setting `MOCK_ENTRA_ISSUER` to one form while that stays the
other *is* the mismatch, and `{"issuer": "..."}` on a single mint is the same thing for one token.
What is genuinely unreachable is a tenant whose *discovery document* disagrees with its own tokens
— and Chemclaw3 never reads discovery, so modelling that would mock a document with no reader.

### Breaking the tenant on purpose

A token that should be refused is only half of the failure surface. The other half is the tenant
*itself* failing, and Chemclaw3's front door treats that as a different thing: an unreachable or
unusable JWKS is a **503 "identity provider unavailable"**, never a 401, because an IdP outage is
the deployment's failure and not a chemist's bad credential. Its
`tests/test_entra_end_to_end.py` proves those paths in-process against a throwaway issuer and names
this surface as the companion for the live lane — so until these controls existed, the live lane
could only ever run the happy path.

Three behaviours, mirroring that file one for one:

```bash
MOCK_ENTRA_ENABLED=true MOCK_ENTRA_FAULT_INJECTION=true uvicorn app.main:app --port 8090

# the tenant is down: the keys endpoint 5xxs, which PyJWT's JWKS client raises as a connection
# error and Chemclaw3 answers 503 for
curl -sX POST localhost:8090/entra/mock-tenant/_control/jwks-fault \
  -H 'content-type: application/json' -d '{"fault":"unavailable"}'

# the tenant answers 200 with something that is not a key set — `malformed` is an intercepting
# proxy's HTML page (dies in `json.load`), `not_a_key_set` is valid JSON that is not a JWKS (dies
# in `PyJWKSet.from_dict`). Two shapes because they fail in two different libraries.
curl -sX POST localhost:8090/entra/mock-tenant/_control/jwks-fault \
  -H 'content-type: application/json' -d '{"fault":"not_a_key_set"}'

# put it back
curl -sX POST localhost:8090/entra/mock-tenant/_control/jwks-fault \
  -H 'content-type: application/json' -d '{"fault":"none"}'

# rotate: a new signing key is published *beside* the old one and mints from now on, so tokens
# issued a minute ago keep validating and a resource server follows by refreshing its key set
curl -sX POST localhost:8090/entra/mock-tenant/_control/rotate-signing-key
```

Both controls answer with the tenant's whole state — `jwks_fault`, `signing_kid`,
`published_kids` — because that is the next thing a driver needs either way.

**They are behind their own switch, and that is the security decision worth stating.**
`MOCK_ENTRA_ENABLED` turns on minting, which decides *who* gets in. Arming a fault decides whether
**anyone** does, for every service that trusts this issuer, and the keys endpoint answers whether
or not minting is enabled — so an unauthenticated control of that reach is a denial-of-service
switch for anything that can open a socket to this process. `MOCK_ENTRA_FAULT_INJECTION` is
therefore off by default and the routes are a 404 naming the variable until it is on. The route
back from an armed fault is the control route — `{"fault":"none"}` above — or a restart, which is
why both controls answer with the tenant's whole state. **Not** the environment variable: this
process reads its environment once, at import, so unsetting `MOCK_ENTRA_FAULT_INJECTION` in a live
shell leaves the keys endpoint 503ing exactly as before (measured). A fault is
also never inferred — an unrecognised name is a 422, not a quietly healthy tenant a lane would
read as "the failure path passed".

`tests/test_entra_faults.py` drives all three through a real `uvicorn` socket with PyJWT's own
`PyJWKClient`, because what matters is not that the route returned 503 but that the client raises
the exception class Chemclaw3 maps to one — and that mapping happens inside `urllib`, which the
in-process ASGI tests never reach.

### An armed fault is invisible to a *warm* front door

This is the part a live lane has to plan around, and it is a property of the reading side rather
than a defect here. Chemclaw3's `api/auth.py::_client_for` keeps one `PyJWKClient` per endpoint for
the process lifetime and passes only `timeout=`, so PyJWT's defaults — `cache_jwk_set=True,
lifespan=300` — apply, and `get_signing_keys()` answers from the cached document without touching
a socket. Once **one** token has validated, this tenant is not consulted again for five minutes.

Measured against Chemclaw3's production `create_app()` with `entra_required=True` pointed at this
mock, nothing patched but the model: cold `POST /sessions` → 200, which warms the key set; then
`unavailable`, `malformed` and `not_a_key_set` armed in turn, with the tenant confirming each in
its control response → 200, 200, 200. Rebuilt at `lifespan=2`, the same probe gives 200 at t+0 and
503 at t+2.5 s — so the blind window is exactly the lifespan, not a permanent hole.

Three ways to drive the 503, cheapest first:

1. **Mint under a `kid` the front door has never seen** — rotate, then mint. An unknown `kid` sends
   PyJWT's `get_signing_key` past its own cache to this tenant, where the armed fault is waiting.
   Chemclaw3 bounds that to one forced refresh per `entra_jwks_refresh_cooldown_seconds` (60 s).
2. **Arm the fault before the front door has validated anything.** A cold key set fetches — which
   is what both repositories' in-process tests get, and what a freshly started `make live-up` gets.
3. **Wait out the 300 s lifespan**, or restart the front door.

```bash
curl -sX POST localhost:8090/entra/mock-tenant/_control/jwks-fault \
  -H 'content-type: application/json' -d '{"fault":"unavailable"}'
curl -sX POST localhost:8090/entra/mock-tenant/_control/rotate-signing-key
curl -sX POST localhost:8090/entra/mock-tenant/oauth2/v2.0/token \
  -H 'content-type: application/json' -d '{"oid":"u-alice"}'   # signed by the new kid
```

`test_an_armed_fault_is_invisible_to_a_warm_key_set_until_a_refresh_is_forced` pins both halves —
that a warm client is blind while the tenant really is 503ing, and that a rotation plus a mint
makes the fault reach it — and it asserts PyJWT's 300 s default, so a dependency bump that moves
the window turns this section red rather than leaving it quietly wrong.

The asymmetry is worth stating: the **rotation** control has always worked live for the same
reason the faults do not. It changes the `kid`, and an unknown `kid` is precisely what bypasses the
cache.

## Wiring a Chemclaw3 checkout to this backend

Add to Chemclaw3's `.env` (or export directly):

```bash
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
uvicorn app.main:app --port 8090
```

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

Covers the ELN list/append/reset endpoints, the stand-in Entra tenant's accept and reject paths,
its injected faults (against a real socket, `tests/test_entra_faults.py`), and the vendor MCP tool. The ELN fixtures themselves were
additionally verified against Chemclaw3's real `JsonExportAdapter`/`OrdJsonAdapter` classes
directly (not just shape assertions here) — both parsed all seeded entries with zero mapping
errors.

## CI

`Jenkinsfile` is this repository's first automated check of any kind. It installs, runs the suite,
and then does the one thing the suite cannot: **starts both processes through their own start
scripts** and asks each of them a question. Every test here drives the app in-process through ASGI,
so `start.sh` and `start-mcp.sh` — including the `.venv` path they hardcode, and which the
four-repository e2e lane actually invokes — were exercised by nothing.

The backend is asked for `/healthz`. The vendor MCP server has no health route, so it is asked
whether its transport is up at all: a bare POST to `/mcp` is not a valid MCP `initialize`, so any
HTTP status (406, in practice) means the port is open and speaking, and only a connection failure
is a failure.

**It publishes no image and deploys nowhere, and that is the design rather than a gap.** This is a
test double. Beside the real integrations it would give the system two answers to one question, so
no environment above `dev` runs it and no release descriptor names it. See Chemclaw3's
`deploy/jenkins/README.md` and `D-2026-08-26-a-release-is-a-descriptor-and-a-target`. It runs in the
local lane, which is where a double belongs.

**It does build the image.** A local kind cluster runs the double in-cluster from `Containerfile`.
The image is built on the developer's machine and loaded with `kind load`, so the stage
`Image builds and both processes answer` builds it and checks it the same way the start scripts
are checked. It starts both processes as a UID the image did not create, in group 0. The backend
has to answer `/healthz` and seed both export dirs, and the vendor's `/mcp` has to answer. The tag
is per-run and removed afterwards. Nothing is pushed, and there is no registry parameter. Building
an image is not a deploy: that needs a published artifact that something names, and this pipeline
produces neither.

### The dependency audit

The last stage runs `pip-audit`, blocking, over the dependency closure the build just installed —
this repository had no supply-chain check of any kind, in any form. It is in the Jenkinsfile rather
than in a GitHub Actions workflow because there are no workflows here: a job nobody runs is a
control that reads as one and is not.

**There is no lockfile, and that bounds what the audit means.** `pyproject.toml` carries ranges, so
there is no recorded set of exact versions to scan; what is scanned instead is the environment the
`Install` stage resolved — the same one the suite ran against and the same one `start.sh` runs —
frozen to a pin list. So a green audit is evidence about *this build*, not about the next one,
which will resolve a different set from the same ranges. The tool is installed into its own venv so
that its dependencies are not part of what it audits.

`.github/dependabot.yml` sits beside it and does the other half: the audit detects, Dependabot
proposes the bump. With open lower bounds and no lockfile, its reach is the constraints in
`pyproject.toml` — mostly the pinned upper bound and any advisory whose fix a range excludes — so
the two are complements, not alternatives.

## Configuration reference (this backend's own env vars)

| Variable | Default | Meaning |
|---|---|---|
| `MOCK_ELN_EXPORT_DIR` | `./data/eln/exports` | Where free-text fixtures are seeded |
| `MOCK_ORD_EXPORT_DIR` | `./data/eln/exports/ord` | Where ORD fixtures are seeded |
| `MOCK_ELN_SEED_ON_STARTUP` | `true` | Seed (and clear) both directories when the app starts |
| `MOCK_HTE_MAX_RECORDS_PER_DATASET` | `0` (unlimited) | Cap each real HTE dataset (`app/eln/real_hte.py`) to its first N rows; real rows only truncated, never fabricated |
| `MOCK_MCP_VENDOR_HOST` / `MOCK_MCP_VENDOR_PORT` | `0.0.0.0` / `8091` | Bind address for the vendor MCP server |
| `MOCK_ENTRA_ENABLED` | `false` | Mint tokens from the stand-in tenant (the keys endpoint answers either way) |
| `MOCK_ENTRA_ISSUER` | `http://127.0.0.1:8090/entra/mock-tenant/v2.0` | The `iss` minted tokens claim; must equal `CHEMCLAW_ENTRA_ISSUER` |
| `MOCK_ENTRA_AUDIENCE` | `api://chemclaw` | The `aud` minted tokens carry; must equal `CHEMCLAW_ENTRA_AUDIENCE` |
| `MOCK_ENTRA_PRIVATE_KEY_PEM` | *(empty)* | A fixed signing key, for a lane whose tokens must survive a restart. Empty generates one per start |
| `MOCK_ENTRA_FAULT_INJECTION` | `false` | Expose the `_control` routes that break the keys endpoint or rotate the signing key (see "Breaking the tenant on purpose") |
