"""Operator CLI for the alerts evaluator.

    docker exec cpi-api-1 python -m app.services.alerts.cli evaluate DA
    docker exec cpi-api-1 python -m app.services.alerts.cli evaluate DA --dry-run
    docker exec cpi-api-1 python -m app.services.alerts.cli backfill DA --pairs 60
    docker exec cpi-api-1 python -m app.services.alerts.cli tenants

Exists so the engine can be proven — real rows, real numbers — before a line of
API or frontend code is written, and so a backfill can be run without going
through an HTTP worker.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from app.services.alerts import runner


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _resolve(code: str) -> tuple[str, str]:
    code = code.strip().upper()
    for tenant_id, tcode in runner.list_alert_tenants():
        if tcode == code:
            return tenant_id, tcode
    # Fall back to a direct lookup so an operator can evaluate a tenant that is
    # not in CPI_ALERTS_TENANT_CODES yet — useful for checking what a tenant
    # would produce before switching it on.
    from sqlalchemy import text
    from app.core.database import SessionLocal
    from app.services.alerts.views import is_alertable

    if not is_alertable(code):
        sys.exit(f"tenant {code} has no snapshot view registered for alerting")
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id FROM tenant WHERE upper(slug) = :c"), {"c": code}
        ).first()
    finally:
        db.close()
    if row is None:
        sys.exit(f"no tenant with code {code}")
    return str(row.id), code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="alerts")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("tenants", help="list tenants alerting runs for")

    ev = sub.add_parser("evaluate", help="evaluate the newest capture pair")
    ev.add_argument("tenant_code")
    ev.add_argument("--cap-date", type=date.fromisoformat, default=None)
    ev.add_argument("--dry-run", action="store_true")
    ev.add_argument("--force", action="store_true",
                    help="evaluate a tenant that has not enabled alerting")

    bf = sub.add_parser("backfill", help="evaluate the last N capture pairs")
    bf.add_argument("tenant_code")
    bf.add_argument("--pairs", type=int, default=60)
    bf.add_argument("--mark-read-before-pairs", type=int, default=5)
    bf.add_argument("--force", action="store_true",
                    help="backfill a tenant that has not enabled alerting")

    args = parser.parse_args(argv)

    if args.cmd == "tenants":
        _print([{"tenant_id": t, "code": c} for t, c in runner.list_alert_tenants()])
        return 0

    tenant_id, code = _resolve(args.tenant_code)

    if args.cmd == "evaluate":
        try:
            summary = runner.run_latest(
                tenant_id, code, cap_date=args.cap_date,
                dry_run=args.dry_run, force=args.force)
        except runner.AlertsNotEnabled as exc:
            sys.exit(f"{exc} (pass --force to evaluate it anyway)")
        _print(summary.to_dict())
        return 0

    if args.cmd == "backfill":
        try:
            _print(runner.run_backfill(
                tenant_id, code,
                pairs=args.pairs,
                mark_read_before_pairs=args.mark_read_before_pairs,
                force=args.force))
        except runner.AlertsNotEnabled as exc:
            sys.exit(f"{exc} (pass --force to backfill it anyway)")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
