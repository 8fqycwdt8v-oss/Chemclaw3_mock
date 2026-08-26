// The mock's pipeline: gate it, and prove both processes still start.
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
// descriptor names it (`D-2026-08-26-a-release-is-a-descriptor-and-a-target` in Chemclaw3). Where a
// dev environment wants it in-cluster, it needs an image and a chart first — neither exists here,
// and inventing them for a double nobody has asked to deploy would be the wrong order of work.
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
  }

  post {
    always {
      archiveArtifacts artifacts: '.smoke-*.log', allowEmptyArchive: true
      sh 'rm -rf .smoke .smoke-*.log || true'
    }
  }
}
