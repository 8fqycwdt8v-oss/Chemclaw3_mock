"""The tenant's injectable faults: what its keys endpoint is currently doing wrong, if anything.

**Why a mock IdP needs a way to fail.** Chemclaw3's front door does not merely fetch this tenant's
JWKS — it distinguishes *how* that fetch failed, and answers 503 ("identity provider unavailable")
rather than 401 whenever the tenant is unreachable or answers with something that is not a key set,
because an IdP outage is the deployment's failure and not a chemist's bad credential.
`tests/test_entra_end_to_end.py` in the Chemclaw3 checkout proves those paths in-process against a
throwaway issuer and names *this* surface as its companion for the live lane — but a tenant that
can only succeed cannot stand in for the failures, so the live lane exercised the happy path alone.
These faults close that: the same three behaviours, over a real socket.

**Two switches, not one, and this is the second.** `MOCK_ENTRA_ENABLED` turns on minting, which
decides *who* can get in. Arming a fault decides whether **anyone** can, for every service that
trusts this issuer, and the keys route is served whether or not minting is enabled — so an
unauthenticated control that could break authentication for a whole stack is a denial-of-service
switch reachable by anything that can open a socket to this process. It is therefore off by
default, refused with a 404 naming the variable, and read again *at serve time*: turning
`MOCK_ENTRA_FAULT_INJECTION` off puts the tenant back to healthy immediately, so a lane can never
be left with a tenant that refuses everybody and no route to fix it.
"""

from typing import Literal, get_args

from app.config import settings

#: What the keys endpoint serves. `none` is the real key set; each other value is one of the two
#: failure shapes Chemclaw3 maps onto a 503.
JwksFault = Literal["none", "unavailable", "malformed", "not_a_key_set"]

#: Every value the control route accepts, for the route's own error message.
JWKS_FAULTS: tuple[str, ...] = get_args(JwksFault)

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

    Consulting the switch here rather than only in the control route is what makes turning it off a
    recovery: the fault is stored, but it is never *served* by a process whose operator has taken
    the capability away.
    """
    return _armed if settings.entra_fault_injection else "none"


def reset() -> None:
    """Disarm. The suite's fixtures call this; the state is module-scoped and outlives a test."""
    arm("none")
