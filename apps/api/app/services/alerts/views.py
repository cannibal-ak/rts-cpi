"""Tenant code → snapshot view whitelist for the alerts evaluator.

View names are interpolated into raw SQL, so they may only ever come from a
whitelist. `airline.py` already owns the canonical map, but it is duplicated
inline three more times in that module (lines ~106, ~205, ~253) and its own
comment documents the duplication as known debt. Adding a fifth copy here would
make that worse, so this module derives from the canonical one instead and a
test asserts the two cannot drift.

Deriving rather than re-declaring also means onboarding a tenant to alerting is
one entry in `AIRLINE_VIEW_MAP` plus one env var, never a second place to
forget.
"""
from __future__ import annotations

from app.routers.airline import AIRLINE_VIEW_MAP

# A straight alias today. It exists as a separate name so that if alerting ever
# needs to read a different relation for some tenant (a materialised rollup,
# say), that divergence has somewhere to live that is not the grid's whitelist.
ALERT_VIEW_MAP: dict[str, str] = dict(AIRLINE_VIEW_MAP)


class UnknownTenantView(KeyError):
    """Raised when a tenant code has no whitelisted snapshot view."""


def resolve_view(tenant_code: str) -> str:
    """Return the snapshot view for a tenant code, or raise.

    Raising rather than returning a default is deliberate: a default would mean
    silently evaluating one tenant's rules against another tenant's fares.
    """
    code = (tenant_code or "").strip().upper()
    try:
        return ALERT_VIEW_MAP[code]
    except KeyError as exc:
        raise UnknownTenantView(
            f"tenant {code!r} has no snapshot view registered for alerting"
        ) from exc


def is_alertable(tenant_code: str) -> bool:
    return (tenant_code or "").strip().upper() in ALERT_VIEW_MAP
