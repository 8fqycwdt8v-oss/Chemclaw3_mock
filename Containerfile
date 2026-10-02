# One image for both of this repository's processes, chosen by the command:
#
#   docker run chemclaw/mock:kind                 # ./start.sh     — ELN/ORD/Entra backend on :8090
#   docker run chemclaw/mock:kind ./start-mcp.sh  # the vendor MCP server on :8091
#
# **The image runs the start scripts, not a reimplementation of them.** They are what the
# four-repository e2e lane runs and what the Jenkinsfile's `Both processes start` stage proves, so
# the image lays the tree out exactly as a checkout is laid out — `/app/app`, `/app/start.sh`,
# `/app/.venv` — and the scripts' hardcoded `$SCRIPT_DIR/.venv/bin/python` resolves unchanged. That
# includes the backend seeding `MOCK_ELN_EXPORT_DIR` / `MOCK_ORD_EXPORT_DIR` on start: `start.sh`
# creates both directories and the app's lifespan seeds them, in the image as on a laptop.
#
# **It is still a test double, and building it is not deploying it.** See README.md §CI: no
# environment above `dev` runs it and no release descriptor names it. The image exists so a local
# cluster (kind) can run the double in-cluster beside the real system; nothing publishes it.
#
# The base is pinned by digest (the multi-arch index of python:3.11-slim), so a rebuild gets the
# reviewed bytes or fails rather than whatever the tag points at that day. Refresh it deliberately:
#
#   docker buildx imagetools inspect python:3.11-slim   # -> Digest: sha256:...
#
# **The Python dependencies are not pinned, and that is this repository's existing posture, not a
# new gap.** There is no lockfile here (see `.github/dependabot.yml` and the Jenkinsfile's
# `Dependency audit`): `pyproject.toml` carries ranges and the build resolves them, so two builds of
# one commit can differ. The resolved set is frozen into the image at /app/requirements.lock.txt so
# what a given image contains is at least *named*.
ARG BASE_IMAGE=docker.io/library/python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b

FROM ${BASE_IMAGE} AS build
WORKDIR /app
COPY pyproject.toml ./
# Dependencies only, read out of pyproject.toml: the project itself is *not* installed. The start
# scripts run `python -m uvicorn app.main:app` from /app, so `app` is imported from the tree, and the
# seed CSVs under app/eln/real_data/ are read relative to it — a wheel would not carry them (no
# package-data is declared), and two copies of `app` on sys.path would be a trap.
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" \
        > /tmp/requirements.in \
    && python -m venv /app/.venv \
    && /app/.venv/bin/python -m pip install --no-cache-dir --upgrade pip \
    && /app/.venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.in \
    && /app/.venv/bin/python -m pip freeze > /app/requirements.lock.txt

FROM ${BASE_IMAGE}
ARG UID=1001
# Non-root, with group 0 owning everything the process writes, so it runs both as UID 1001 and
# under an arbitrary high UID (OpenShift's restricted SCC, which keeps GID 0) — the same posture as
# Chemclaw3's own image.
RUN useradd --uid ${UID} --gid 0 --no-create-home --home-dir /app --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/requirements.lock.txt /app/requirements.lock.txt
COPY app ./app
COPY start.sh start-mcp.sh healthcheck.py ./
# /app/data is where both export dirs default to (`./data/eln/exports`, `.../ord`); a deployment
# that shares them with Chemclaw3 mounts a volume and sets MOCK_ELN_EXPORT_DIR/MOCK_ORD_EXPORT_DIR.
# Either way the directory must be writable by the runtime UID, and the code must not be.
RUN mkdir -p /app/data/eln/exports/ord \
    && chown -R ${UID}:0 /app/data \
    && chmod -R g=u /app/data \
    && chmod 0755 start.sh start-mcp.sh \
    && /app/.venv/bin/python -c "import app.main, app.mcp_tools.vendor_server" \
    && echo "both entry modules import"
USER ${UID}
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MOCK_SERVER_PORT=8090 \
    MOCK_MCP_VENDOR_PORT=8091
EXPOSE 8090 8091
# One check for whichever process the command started: the backend's /healthz, else the vendor's
# MCP transport (it has no health route). See healthcheck.py.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/app/.venv/bin/python", "/app/healthcheck.py"]
CMD ["./start.sh"]
