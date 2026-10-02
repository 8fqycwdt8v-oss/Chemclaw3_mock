"""The container healthcheck, for whichever of the two processes the image was started as.

The image runs either `start.sh` (the backend, which has `/healthz`) or `start-mcp.sh` (the vendor
MCP server, which has no health route). The same question the Jenkinsfile asks each is asked here:
the backend must answer `/healthz` with 200; the vendor must answer *any* HTTP status on `/mcp`,
because a bare POST is not a valid MCP `initialize` and the point is only that the transport is up.
A connection failure on both ports is unhealthy.

The backend serves TLS when `MOCK_SSL_CERTFILE` is set (`start.sh`; the browser sign-in flow needs
it), so the probe follows: https on loopback with verification off, because the certificate is a
throwaway the probe has no reason to trust and the question is only whether the process answers.
"""

import os
import ssl
import sys
import urllib.error
import urllib.request

_TLS = bool(os.environ.get("MOCK_SSL_CERTFILE"))
_BACKEND = f"{'https' if _TLS else 'http'}://127.0.0.1:{os.environ.get('MOCK_SERVER_PORT', '8090')}/healthz"
_VENDOR = f"http://127.0.0.1:{os.environ.get('MOCK_MCP_VENDOR_PORT', '8091')}/mcp"


def _backend_healthy() -> bool:
    try:
        context = ssl._create_unverified_context() if _TLS else None  # noqa: S323 - loopback probe
        with urllib.request.urlopen(_BACKEND, timeout=3, context=context) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _vendor_answering() -> bool:
    request = urllib.request.Request(
        _VENDOR, data=b"{}", headers={"content-type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=3):
            return True
    except urllib.error.HTTPError:
        return True  # any status at all: the transport is up
    except (urllib.error.URLError, OSError):
        return False


if __name__ == "__main__":
    sys.exit(0 if _backend_healthy() or _vendor_answering() else 1)
