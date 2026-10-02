// The mock's pipeline: gate it, prove both processes still start, and audit what it installed.
//
// **This repository has had no CI of any kind.** Its test modules — the ELN sources, the stand-in
// Entra tenant, the vendor MCP tool — run only when somebody remembers. That
// is the gap this closes, and it is a bigger one than it looks: the four-repository e2e lane
// (`infra/live/e2e-full-stack/up.sh` in the Chemclaw3 checkout) is what proves the *real* system
// end to end, and it proves it against these processes. A broken mock reads as a broken backend.
//
// **It publishes nothing and deploys nowhere, deliberately.** This is a test double: a stand-in
// ELN source, Entra tenant and vendor MCP tool. Beside the real integrations it would give
// the system two answers to one question, so no environment above `dev` runs it and no release
// descriptor names it (`D-2026-08-26-a-release-is-a-descriptor-and-a-target` in Chemclaw3).
//
// **It does build the image, and that does not change the line above.** A local kind cluster runs
// the double in-cluster from `Containerfile`, built on the developer's machine and loaded with
// `kind load`, so the image is checked here the way the start scripts are: it is built, both of
// its processes are started, and both answer. The build is tagged per run and removed afterwards.
// Nothing is pushed, there is no registry parameter, and no chart lives here. An image only
// becomes a deploy once it is published and named somewhere, and this pipeline does neither.
pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30'))
    timeout(time: 30, unit: 'MINUTES')
  }

  parameters {
    string(name: 'PYTHON', defaultValue: 'python3.11',
           description: 'Interpreter to build the venv with. The floor is 3.11 (pyproject).')
  }

  stages {
    stage('Install') {
      steps {
        sh '''
          set -euo pipefail
          "${PYTHON:-python3.11}" -m venv .venv
          .venv/bin/python -m pip install --upgrade pip
          # The `mcp<2` cap in pyproject is load-bearing, not tidiness: 2.0 removed
          # `mcp.server.fastmcp`, which `app/mcp_tools/vendor_server.py` imports FastMCP from, so an
          # unbounded install resolves 2.x and the vendor server dies at import with no code change.
          .venv/bin/python -m pip install -e '.[dev]'
        '''
      }
    }

    stage('Test') {
      steps {
        sh '.venv/bin/python -m pytest -q'
      }
    }

    // Every test above drives the app through ASGI in-process. Neither start script is exercised by
    // any of them, and both are what the e2e lane actually runs — including the venv path they
    // hardcode, which no in-process test can be wrong about.
    stage('Both processes start') {
      steps {
        sh '''
          set -euo pipefail
          export MOCK_SERVER_PORT=18090 MOCK_MCP_VENDOR_PORT=18091
          export MOCK_ELN_EXPORT_DIR="${WORKSPACE}/.smoke/eln" MOCK_ORD_EXPORT_DIR="${WORKSPACE}/.smoke/ord"

          ./start.sh > .smoke-backend.log 2>&1 &
          backend=$!
          ./start-mcp.sh > .smoke-vendor.log 2>&1 &
          vendor=$!
          trap 'kill "${backend}" "${vendor}" 2>/dev/null || true' EXIT

          for _ in $(seq 1 30); do
            curl -sf "http://127.0.0.1:${MOCK_SERVER_PORT}/healthz" >/dev/null && break || sleep 1
          done
          curl -sf "http://127.0.0.1:${MOCK_SERVER_PORT}/healthz" \
            || { echo "the mock backend did not answer /healthz" >&2; cat .smoke-backend.log; exit 1; }

          # The vendor server speaks MCP and has no health route, so the question asked of it is the
          # one that matters: is the port open and answering? A bare POST is not a valid MCP
          # `initialize`, so any HTTP status at all means the transport is up.
          for _ in $(seq 1 30); do
            curl -s -o /dev/null "http://127.0.0.1:${MOCK_MCP_VENDOR_PORT}/mcp" && break || sleep 1
          done
          code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST \
            -H 'content-type: application/json' -d '{}' "http://127.0.0.1:${MOCK_MCP_VENDOR_PORT}/mcp" || echo 000)"
          test "${code}" != "000" \
            || { echo "the vendor MCP server never answered" >&2; cat .smoke-vendor.log; exit 1; }
          echo "backend and vendor MCP server both start (vendor /mcp answered ${code})"
        '''
      }
    }

    // The image (`Containerfile`) is built and run here, and pushed nowhere. A local cluster (kind)
    // runs this double in-cluster from a locally built and loaded image, so the image has to work.
    // Before this stage nothing built it, and a broken image showed up as a broken backend at
    // `kind load` time. The stage asks the same questions as the one above, this time of the
    // image: the backend answers `/healthz` and has seeded both export dirs, and the vendor's MCP
    // transport answers. Both run as a UID the image did not create (in group 0, the
    // OpenShift-restricted shape), because a double that only runs as its own UID is not rootless
    // in the way a cluster means it. No registry, no credential, no tag beyond this build.
    stage('Image builds and both processes answer') {
      steps {
        sh '''
          set -euo pipefail
          runner="$(command -v docker || command -v podman || true)"
          if [ -z "${runner}" ]; then
            echo "no docker or podman on this agent: the image stage cannot run here" >&2
            exit 1
          fi
          image="chemclaw3-mock:ci-${BUILD_NUMBER:-local}"
          "${runner}" build -f Containerfile -t "${image}" .
          cleanup() {
            "${runner}" rm -f mock-ci-backend-${BUILD_NUMBER:-local} mock-ci-vendor-${BUILD_NUMBER:-local} >/dev/null 2>&1 || true
            "${runner}" rmi -f "${image}" >/dev/null 2>&1 || true
          }
          trap cleanup EXIT

          "${runner}" run -d --name mock-ci-backend-${BUILD_NUMBER:-local} --user 100123:0 \
            -e MOCK_HTE_MAX_RECORDS_PER_DATASET=5 -p 127.0.0.1::8090 "${image}" >/dev/null
          "${runner}" run -d --name mock-ci-vendor-${BUILD_NUMBER:-local} --user 100123:0 \
            -p 127.0.0.1::8091 "${image}" ./start-mcp.sh >/dev/null
          backend_port="$("${runner}" port mock-ci-backend-${BUILD_NUMBER:-local} 8090 | head -1 | sed 's/.*://')"
          vendor_port="$("${runner}" port mock-ci-vendor-${BUILD_NUMBER:-local} 8091 | head -1 | sed 's/.*://')"

          for _ in $(seq 1 60); do
            curl -sf "http://127.0.0.1:${backend_port}/healthz" >/dev/null && break || sleep 1
          done
          curl -sf "http://127.0.0.1:${backend_port}/healthz" \
            || { echo "the image's backend did not answer /healthz" >&2; "${runner}" logs mock-ci-backend-${BUILD_NUMBER:-local}; exit 1; }
          seeded="$("${runner}" exec mock-ci-backend-${BUILD_NUMBER:-local} sh -c \
            'ls /app/data/eln/exports/*.json | wc -l; ls /app/data/eln/exports/ord/*.json | wc -l')"
          echo "seeded entries (eln, ord): $(echo ${seeded})"
          for n in ${seeded}; do
            test "${n}" -gt 0 || { echo "the image's backend started but seeded an empty export dir" >&2; exit 1; }
          done

          for _ in $(seq 1 30); do
            curl -s -o /dev/null "http://127.0.0.1:${vendor_port}/mcp" && break || sleep 1
          done
          code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST \
            -H 'content-type: application/json' -d '{}' "http://127.0.0.1:${vendor_port}/mcp" || echo 000)"
          test "${code}" != "000" \
            || { echo "the image's vendor MCP server never answered" >&2; "${runner}" logs mock-ci-vendor-${BUILD_NUMBER:-local}; exit 1; }
          echo "image: backend healthy and seeded, vendor /mcp answered ${code}"
        '''
      }
    }

    // **Nothing here checked the dependency closure for known vulnerabilities, in any form.** There
    // is no `.github/workflows/`, so a GitHub Actions job would be a control that reads as one and
    // never runs; this pipeline is where this repository's CI actually lives, so this is where the
    // check goes. Blocking, like the sibling Chemclaw3 checkout's `deps-audit`, which is there
    // because that pattern caught real advisories.
    //
    // **What it can and cannot see, stated rather than implied: this repository has no lockfile.**
    // `pyproject.toml` carries ranges (`fastapi>=0.115`, `mcp>=1.2,<2`), so there is no recorded
    // set of exact versions to audit. What is audited instead is the environment the `Install`
    // stage just resolved — the same one the suite ran against and the same one `start.sh` runs,
    // frozen to a pin list here. That is the honest maximum: it catches a vulnerable version at
    // the moment this build resolved it, and it is *not* reproducible, because tomorrow's build
    // resolves a different set from the same ranges. A green audit is evidence about this build,
    // never about the next one.
    //
    // `pip-audit` goes in its own venv on purpose: installed beside the app, its own dependency
    // closure would join the audited set and a finding against one of *its* libraries would fail
    // this build for something this repository does not ship.
    //
    // `--no-deps --disable-pip` because `pip freeze` already emits the fully-resolved set —
    // re-resolving would audit a different closure than the one that was just tested. The project
    // itself is excluded because it is installed editable and is not on PyPI, so it is the one
    // distribution that can never be looked up.
    //
    // A found vulnerability and an unreachable advisory database share an exit code (1), and
    // unlike Chemclaw3's `make deps-audit` this stage does not classify them: that target has to
    // stay usable on a laptop with no network, and this one only ever runs in CI — where an
    // unreachable database is a supply-chain check that silently did not happen, which is exactly
    // the shape this stage exists to close. Both fail the build.
    stage('Dependency audit') {
      steps {
        sh '''
          set -euo pipefail
          "${PYTHON:-python3.11}" -m venv .venv-audit
          .venv-audit/bin/python -m pip install --upgrade pip
          .venv-audit/bin/python -m pip install pip-audit

          .venv/bin/python -m pip freeze --exclude-editable > .audit-requirements.txt
          echo "auditing $(wc -l < .audit-requirements.txt) resolved distributions"
          .venv-audit/bin/pip-audit --no-deps --disable-pip --progress-spinner=off -r .audit-requirements.txt
        '''
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: '.smoke-*.log,.audit-requirements.txt', allowEmptyArchive: true
      sh 'rm -rf .smoke .smoke-*.log .audit-requirements.txt .venv-audit || true'
    }
  }
}
