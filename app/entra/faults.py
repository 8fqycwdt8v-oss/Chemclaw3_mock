"""The tenant's injectable faults: what its keys endpoint is currently doing wrong, if anything.

**Why a mock IdP needs a way to fail.** Chemclaw3's front door does not merely fetch this tenant's
JWKS — it distinguishes *how* that fetch failed, and answers 503 ("identity provider unavailable")
rather than 401 whenever the tenant is unreachable or answers with something that is not a key set,
because an IdP outage is the deployment's failure and not a chemist's bad credential.
`tests/test_entra_end_to_end.py` in the Chemclaw3 checkout proves those paths in-process against a
throwaway issuer and names *this* surface as its companion for the live lane — but a tenant that
can only succeed cannot stand in for the failures, so the live lane exercised the happy path alone.
These faults close that: the same three behaviours, over a real socket.

**What an armed fault does *not* do is break a front door that has already validated a token.**
`api/auth.py::_client_for` there keeps one `PyJWKClient` per endpoint for the process lifetime with
PyJWT's `cache_jwk_set=True, lifespan=300`, so a warm key set answers from memory and this tenant
is not consulted again for five minutes — measured: with each fault armed, that front door still
answers 200. Arming one is observable promptly only to a caller who has not fetched yet, or via a
`kid` it has never seen (`_control/rotate-signing-key`, then mint), which is what sends
`get_signing_key` past its own cache. `README.md`'s "invisible to a warm front door" section is the
recipe, and `tests/test_entra_faults.py` pins both halves.

**Two switches, not one, and this is the second.** `MOCK_ENTRA_ENABLED` turns on minting, which
decides *who* can get in. Arming a fault decides whether **anyone** can, for every service that
trusts this issuer, and the keys route is served whether or not minting is enabled — so an
unauthenticated control that could break authentication for a whole stack is a denial-of-service
switch reachable by anything that can open a socket to this process. It is therefore off by
default and refused with a 404 naming the variable.

**The route back from an armed fault is the control route — `{"fault": "none"}` — or a restart.**
Not the environment variable: `app/config.py` builds `settings` once at import and reads the
environment there and nowhere else, so unsetting `MOCK_ENTRA_FAULT_INJECTION` in a live shell
changes nothing about what this tenant serves. That is why the arming route answers with the whole
tenant state, and why `router.py`'s 404 says *start this process with* the variable. This docstring
used to call the serve-time check a recovery, which sent a reader to unset a variable nothing reads
again.
"""

from typing import Literal

from app.config import settings

#: What the keys endpoint serves. `none` is the real key set; each other value is one of the two
#: failure shapes Chemclaw3 maps onto a 503.
JwksFault = Literal["none", "unavailable", "malformed", "not_a_key_set"]

#: An intercepting proxy's error page: a 200 whose body is not JSON at all, so a JWKS client dies
#: in `json.load` with a `ValueError`.
MALFORMED_BODY = "<html><body>502 Bad Gateway</body></html>"

#: A tenant answering valid JSON that is not a key set, so a JWKS client gets past `json.load` and
#: dies in `PyJWKSet.from_dict` instead. A different library, and a different exception class.
NOT_A_KEY_SET_BODY = '{"error": "tenant not found"}'

_armed: JwksFault = "none"


def arm(fault: JwksFault) -> None:
    """Make the keys endpoint serve `fault` from now on (`none` restores the real key set)."""
    global _armed
    _armed = fault


def armed() -> JwksFault:
    """The fault in force — always `none` while `MOCK_ENTRA_FAULT_INJECTION` is off.

    One switch read in both places rather than two, so a process that never asked for the
    capability cannot serve a fault whatever else in it calls `arm()`. It is not a live recovery:
    the value comes from settings frozen at import, and the only writer of it in a running process
    is a test's `monkeypatch` — see the module docstring for what does put the tenant back.
    """
    return _armed if settings.entra_fault_injection else "none"


def reset() -> None:
    """Disarm. The suite's fixtures call this; the state is module-scoped and outlives a test."""
    arm("none")
