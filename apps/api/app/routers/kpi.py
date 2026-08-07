"""KPI summary + detail endpoints for the airline CPI dashboard.

Backs the React click-to-expand KPI row (KPICard / KPIDetailPanel / KPIRow).
Each tenant's KPI summary values AND their per-tile detail tables are computed
here so they stay in sync with each other and respond to the Cap Date picker —
previously the summary tiles were Superset big-number charts.

Scope: JY and PW. Both use the same view schema and now expose the same set
of 5 KPIs each (airlines/competitors, markets/routes, own avg fare, competitors
avg fare, dep dates) — JY and PW differ only in label wording. The KPI keys,
SQL, meta and detail builders are kept in a per-airline registry (AIRLINE_CFG).
The cruise/ferry (FJL) view has a different fare schema entirely and is
intentionally not exposed; anything not in the registry returns 422.

Security:
  * Tenant isolation is identity-based, mirroring superset.py. Platform (RTS)
    admins are rejected; a tenant user may only read their own airline_code.
  * cap_date is always a bound parameter (:cap_date). The view name is never
    user-supplied — it comes from the AIRLINE_CFG whitelist (psycopg cannot
    bind an identifier, so the whitelist is what prevents injection).
"""

import logging
import re
from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_user_identity, get_user_roles, is_platform_admin

# app.* loggers are silent in this container — route through uvicorn.error
# (see project logging convention).
_log = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/v1/kpi", tags=["KPI"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_cap_date(value: str) -> str:
    """Strict YYYY-MM-DD validation. 422 on malformed/unreal dates."""
    if not _DATE_RE.match(value or ""):
        raise HTTPException(422, detail={"message": "Invalid cap_date: must be YYYY-MM-DD"})
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, detail={"message": "Invalid cap_date: not a real date"})
    return value


def _i(value: Any) -> int:
    """Coerce a possibly-NULL numeric aggregate to int (NULL -> 0)."""
    return int(value) if value is not None else 0


def _f(value: Any) -> float:
    """Coerce a possibly-NULL numeric aggregate to float (NULL -> 0.0)."""
    return float(value) if value is not None else 0.0


# None-preserving variants — used only on fare AVG/MIN aggregates wrapped in
# NULLIF(col, 0). A 100%-zero group yields NULL from the DB and must surface as
# JSON null (rendered as "—") rather than being coalesced to 0, which would
# masquerade as a real low/avg fare.
def _n_i(value: Any) -> int | None:
    return int(value) if value is not None else None


def _n_f(value: Any) -> float | None:
    return float(value) if value is not None else None


# FJL data spans three regional Color Line / Fjord Line sites, each publishing
# in its local currency. Without a currency filter, fare averages mix EUR/DKK/
# NOK (~8x apart) and counts triple because every route/competitor/date
# appears once per currency. JY/PW have no equivalent dimension.
_FJL_CURRENCIES = frozenset({"NOK", "EUR", "DKK"})
_FJL_DEFAULT_CURRENCY = "NOK"


def _resolve_currency(code: str, currency: str | None) -> str | None:
    """For FJL: default to NOK and validate. For others: ignore (return None)."""
    if code != "FJL":
        return None
    resolved = (currency or _FJL_DEFAULT_CURRENCY).upper()
    if resolved not in _FJL_CURRENCIES:
        raise HTTPException(422, detail={
            "message": f"Invalid currency '{currency}'. Allowed: {sorted(_FJL_CURRENCIES)}",
        })
    return resolved


# ════════════════════════════════════════════════════════════
#  JY KPIs
# ════════════════════════════════════════════════════════════

def _summary_sql_jy(view: str) -> dict[str, str]:
    return {
        "airlines_analyzed": f"""
            SELECT COUNT(DISTINCT comp_al)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "markets_covered": f"""
            SELECT COUNT(DISTINCT ref_org || '-' || ref_dst)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "jy_avg_fare": f"""
            SELECT COALESCE(ROUND(AVG(COALESCE(ref_tot_fare, 0))::numeric, 2), 0)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "competitors_avg_fare": f"""
            SELECT COALESCE(ROUND(AVG(COALESCE(comp_tot_fare, 0))::numeric, 2), 0)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "dep_dates_monitored": f"""
            SELECT COUNT(DISTINCT ref_dep_date)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
    }


_JY_KPI_META = {
    "airlines_analyzed":    {"label": "Airlines Analyzed",    "subheader": "Distinct competitors tracked"},
    "markets_covered":      {"label": "Markets Covered",      "subheader": "Origin-destination pairs analyzed"},
    "jy_avg_fare":          {"label": "JY Avg Fare",          "subheader": "Average JY fare across all routes"},
    "competitors_avg_fare": {"label": "Competitors Avg Fare", "subheader": "Average competitor fare across all routes"},
    "dep_dates_monitored":  {"label": "Dep Dates Monitored",  "subheader": "Future travel dates with pricing data"},
}

# Summary values returned as floats (2dp); everything else is an int.
_JY_FLOAT_KEYS = frozenset({"jy_avg_fare", "competitors_avg_fare"})

# Summary values whose underlying AVG is wrapped in NULLIF — NULL must surface
# as JSON null (rendered as "—") instead of being coerced to 0 by _f/_i.
_JY_NULL_KEYS = frozenset({"jy_avg_fare", "competitors_avg_fare"})


def _detail_jy_airlines(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT comp_al,
               COUNT(DISTINCT ref_org || '-' || ref_dst) AS routes
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY comp_al
        ORDER BY routes DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Competitor", "Routes"],
        "rows": [
            {"rank": i, "comp_al": r[0], "routes": _i(r[1])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_jy_markets(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_org || ' → ' || ref_dst AS route,
               COUNT(DISTINCT comp_al) AS competitors
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_org, ref_dst
        ORDER BY competitors DESC, route
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Route", "Competitors"],
        "rows": [
            {"rank": i, "route": r[0], "competitors": _i(r[1])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_jy_jy_fare(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_org || '-' || ref_dst AS route,
               comp_al,
               COALESCE(ROUND(AVG(COALESCE(ref_tot_fare, 0))::numeric, 0), 0) AS jy_fare,
               COALESCE(ROUND(AVG(COALESCE(comp_tot_fare, 0))::numeric, 0), 0) AS comp_fare,
               COALESCE(ROUND((AVG(COALESCE(ref_tot_fare, 0)) - AVG(COALESCE(comp_tot_fare, 0)))::numeric, 0), 0) AS difference
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_org, ref_dst, comp_al
        ORDER BY jy_fare DESC
        LIMIT 50
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Route", "Competitor", "JY Fare", "Comp Fare", "Difference"],
        "rows": [
            {"rank": i, "route": r[0], "comp_al": r[1], "jy_fare": _i(r[2]),
             "comp_fare": _i(r[3]), "difference": _i(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_jy_comp_fare(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT comp_al,
               COALESCE(ROUND(AVG(COALESCE(comp_tot_fare, 0))::numeric, 0), 0) AS avg_fare,
               COALESCE(ROUND(MIN(COALESCE(comp_tot_fare, 0))::numeric, 0), 0) AS min_fare,
               COALESCE(ROUND(MAX(COALESCE(comp_tot_fare, 0))::numeric, 0), 0) AS max_fare,
               COUNT(DISTINCT ref_org || '-' || ref_dst) AS routes
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY comp_al
        ORDER BY avg_fare DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Competitor", "Avg Fare", "Min Fare", "Max Fare", "Routes"],
        "rows": [
            {"rank": i, "comp_al": r[0], "avg_fare": _i(r[1]),
             "min_fare": _i(r[2]), "max_fare": _i(r[3]), "routes": _i(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_jy_comp_fare_by_route(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_org || '-' || ref_dst AS route,
               COALESCE(ROUND(AVG(COALESCE(comp_tot_fare, 0))::numeric, 0), 0) AS comp_fare,
               COALESCE(ROUND(AVG(COALESCE(ref_tot_fare, 0))::numeric, 0), 0) AS jy_fare
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_org, ref_dst, comp_al
        ORDER BY jy_fare DESC
    """), {"cap_date": cap_date}).fetchall()
    order: list[str] = []
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for route, comp_fare, _jy in rows:
        if route not in counts:
            order.append(route)
            totals[route] = 0.0
            counts[route] = 0
        if comp_fare is not None:
            totals[route] += float(comp_fare)
            counts[route] += 1
    out: list[dict[str, Any]] = []
    rank = 1
    for route in order:
        if counts[route] == 0:
            continue
        out.append({"rank": rank, "route": route, "avg_comp_fare": round(totals[route] / counts[route])})
        rank += 1
    return {
        "columns": ["#", "Route", "Competitors Avg Fare"],
        "rows": out,
    }


def _detail_jy_dep_dates(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_dep_date,
               COUNT(DISTINCT comp_al) AS competitors,
               COUNT(DISTINCT ref_org || '-' || ref_dst) AS routes
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_dep_date
        ORDER BY ref_dep_date DESC
        LIMIT 50
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Dep Date", "Competitors", "Routes"],
        "rows": [
            {"rank": i,
             "ref_dep_date": r[0].isoformat() if r[0] is not None else "",
             "competitors": _i(r[1]), "routes": _i(r[2])}
            for i, r in enumerate(rows, start=1)
        ],
    }


# ════════════════════════════════════════════════════════════
#  PW KPIs
# ════════════════════════════════════════════════════════════

def _summary_sql_pw(view: str) -> dict[str, str]:
    return {
        "competitors_analyzed": f"""
            SELECT COUNT(DISTINCT comp_al)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "routes_covered": f"""
            SELECT COUNT(DISTINCT ref_org || ref_dst)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "pw_avg_fare": f"""
            SELECT COALESCE(ROUND(AVG(COALESCE(ref_tot_fare, 0))::numeric, 2), 0)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "competitors_avg_fare": f"""
            SELECT COALESCE(ROUND(AVG(COALESCE(comp_tot_fare, 0))::numeric, 2), 0)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "dep_dates_monitored": f"""
            SELECT COUNT(DISTINCT ref_dep_date)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
    }


_PW_KPI_META = {
    "competitors_analyzed":  {"label": "Competitors Analyzed", "subheader": "Distinct competitors tracked"},
    "routes_covered":        {"label": "Routes Covered", "subheader": "Origin-destination pairs analyzed"},
    "pw_avg_fare":           {"label": "PW Avg Fare", "subheader": "Average PW fare across all routes"},
    "competitors_avg_fare":  {"label": "Competitors Avg Fare", "subheader": "Average competitor fare across all routes"},
    "dep_dates_monitored":   {"label": "Dep Dates Monitored", "subheader": "Future travel dates with pricing data"},
}

# Summary values returned as floats (2dp). Everything else is an int.
_PW_FLOAT_KEYS = frozenset({"pw_avg_fare", "competitors_avg_fare"})

# See _JY_NULL_KEYS for rationale.
_PW_NULL_KEYS = frozenset({"pw_avg_fare", "competitors_avg_fare"})


def _detail_pw_competitors(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT comp_al,
               COUNT(DISTINCT ref_org || '-' || ref_dst) AS routes,
               ROUND(AVG(NULLIF(comp_tot_fare, 0))::numeric, 0) AS avg_fare,
               ROUND((AVG(NULLIF(comp_tot_fare, 0)) - AVG(NULLIF(ref_tot_fare, 0)))::numeric, 0) AS fare_gap
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY comp_al
        ORDER BY routes DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Competitor", "Routes", "Avg Fare", "Fare Gap"],
        "rows": [
            {"rank": i, "comp_al": r[0], "routes": _i(r[1]),
             "avg_fare": _n_i(r[2]), "fare_gap": _n_i(r[3])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_pw_routes(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_org || ' → ' || ref_dst AS route,
               COUNT(DISTINCT comp_al) AS competitors,
               ROUND(AVG(NULLIF(ref_tot_fare, 0))::numeric, 0) AS pw_avg,
               ROUND(AVG(NULLIF(comp_tot_fare, 0))::numeric, 0) AS comp_avg,
               ROUND((AVG(NULLIF(comp_tot_fare, 0)) - AVG(NULLIF(ref_tot_fare, 0)))::numeric, 0) AS fare_gap
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_org, ref_dst
        ORDER BY competitors DESC, route
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Route", "Competitors", "PW Avg Fare", "Comp Avg Fare", "Fare Gap"],
        "rows": [
            {"rank": i, "route": r[0], "competitors": _i(r[1]),
             "pw_avg": _n_i(r[2]), "comp_avg": _n_i(r[3]), "fare_gap": _n_i(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_pw_pw_fare(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_org || ' → ' || ref_dst AS route,
               ROUND(AVG(NULLIF(ref_tot_fare, 0))::numeric, 0) AS avg_fare,
               ROUND(MIN(NULLIF(ref_tot_fare, 0))::numeric, 0) AS min_fare,
               ROUND(MAX(ref_tot_fare)::numeric, 0) AS max_fare
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_org, ref_dst
        ORDER BY avg_fare DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Route", "PW Avg Fare", "Min Fare", "Max Fare"],
        "rows": [
            {"rank": i, "route": r[0], "avg_fare": _n_i(r[1]),
             "min_fare": _n_i(r[2]), "max_fare": _i(r[3])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_pw_comp_fare(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT comp_al,
               ROUND(AVG(NULLIF(comp_tot_fare, 0))::numeric, 0) AS avg_fare,
               ROUND(MIN(NULLIF(comp_tot_fare, 0))::numeric, 0) AS min_fare,
               ROUND(MAX(comp_tot_fare)::numeric, 0) AS max_fare,
               COUNT(DISTINCT ref_org || '-' || ref_dst) AS routes
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY comp_al
        ORDER BY avg_fare DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Competitor", "Avg Fare", "Min Fare", "Max Fare", "Routes"],
        "rows": [
            {"rank": i, "comp_al": r[0], "avg_fare": _n_i(r[1]),
             "min_fare": _n_i(r[2]), "max_fare": _i(r[3]), "routes": _i(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_pw_dep_dates(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_dep_date,
               COUNT(DISTINCT comp_al) AS competitors,
               COUNT(DISTINCT ref_org || '-' || ref_dst) AS routes
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_dep_date
        ORDER BY ref_dep_date DESC
        LIMIT 50
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Dep Date", "Competitors", "Routes"],
        "rows": [
            {"rank": i,
             "ref_dep_date": r[0].isoformat() if r[0] is not None else "",
             "competitors": _i(r[1]), "routes": _i(r[2])}
            for i, r in enumerate(rows, start=1)
        ],
    }


# ════════════════════════════════════════════════════════════
#  Per-airline registry
# ════════════════════════════════════════════════════════════
# airline_code -> config. The view name is interpolated into SQL, so this
# mapping is the injection guard — never add an unvalidated entry.

# ════════════════════════════════════════════════════════════
#  FJL KPIs (cruise/ferry — competitor website pricing)
# ════════════════════════════════════════════════════════════
# FJL rows come from competitor + own websites (the `source` column), not
# airline GDS data, so the schema differs from JY/PW: competitor = `source`,
# route = org||dest, dates = out_dep_date, and the fare has a richer breakdown
# (total / per-pax / vehicle / cabin). "FJL's own" rows are the fjordline.com
# variants (nb/dk/de); everything else is a competitor — detected with
# strpos(lower(source), 'fjordline') (there is no single own-source value).
# Every SQL filters by :currency so fare averages stay within one currency and
# counts don't multiply by the number of currencies present.


def _summary_sql_fjl(view: str) -> dict[str, str]:
    return {
        "competitors_tracked": f"""
            SELECT COUNT(DISTINCT source)
            FROM {view}
            WHERE cap_date = :cap_date
              AND curr_code = :currency
              AND strpos(lower(source), 'fjordline') = 0
        """,
        "routes_covered": f"""
            SELECT COUNT(DISTINCT org || '-' || dest)
            FROM {view}
            WHERE cap_date = :cap_date
              AND curr_code = :currency
        """,
        "fjl_avg_fare": f"""
            SELECT ROUND(AVG(total_fare)::numeric, 2)
            FROM {view}
            WHERE cap_date = :cap_date
              AND curr_code = :currency
              AND strpos(lower(source), 'fjordline') > 0
        """,
        "competitors_avg_fare": f"""
            SELECT ROUND(AVG(total_fare)::numeric, 2)
            FROM {view}
            WHERE cap_date = :cap_date
              AND curr_code = :currency
              AND strpos(lower(source), 'fjordline') = 0
        """,
        "dep_dates_monitored": f"""
            SELECT COUNT(DISTINCT out_dep_date)
            FROM {view}
            WHERE cap_date = :cap_date
              AND curr_code = :currency
        """,
    }


_FJL_KPI_META = {
    "competitors_tracked":  {"label": "Competitors Tracked", "subheader": "Competitor websites monitored"},
    "routes_covered":       {"label": "Routes Covered", "subheader": "Origin-destination pairs analyzed"},
    "fjl_avg_fare":         {"label": "FJL Avg Fare", "subheader": "Average total fare across all routes"},
    "competitors_avg_fare": {"label": "Competitors Avg Fare", "subheader": "Average competitor fare across all routes"},
    "dep_dates_monitored":  {"label": "Departure Dates Monitored", "subheader": "Future travel dates with pricing data"},
}

# Summary values returned as floats (2dp); everything else is an int.
_FJL_FLOAT_KEYS = frozenset({"fjl_avg_fare", "competitors_avg_fare"})


def _detail_fjl_competitors(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT source,
               COUNT(DISTINCT org || '-' || dest) AS routes
        FROM {view}
        WHERE cap_date = :cap_date
          AND curr_code = :currency
          AND strpos(lower(source), 'fjordline') = 0
        GROUP BY source
        ORDER BY routes DESC, source
    """), {"cap_date": cap_date, "currency": currency}).fetchall()
    return {
        "columns": ["#", "Competitor", "Routes"],
        "rows": [
            {"rank": i, "source": r[0], "routes": _i(r[1])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_fjl_routes(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT org || ' → ' || dest AS route,
               COUNT(DISTINCT source) AS competitors
        FROM {view}
        WHERE cap_date = :cap_date
          AND curr_code = :currency
        GROUP BY org, dest
        ORDER BY competitors DESC, route
    """), {"cap_date": cap_date, "currency": currency}).fetchall()
    return {
        "columns": ["#", "Route", "Competitors"],
        "rows": [
            {"rank": i, "route": r[0], "competitors": _i(r[1])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_fjl_avg_fare(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT org || ' → ' || dest AS route,
               source,
               ROUND(AVG(total_fare)::numeric, 2) AS total_fare,
               ROUND(AVG(out_per_pax_fare)::numeric, 2) AS pax_fare,
               ROUND(AVG(out_veh_fare)::numeric, 2) AS veh_fare,
               ROUND(AVG(out_cab_fare)::numeric, 2) AS cab_fare
        FROM {view}
        WHERE cap_date = :cap_date
          AND curr_code = :currency
        GROUP BY org, dest, source
        ORDER BY total_fare DESC
    """), {"cap_date": cap_date, "currency": currency}).fetchall()
    return {
        "columns": ["#", "Route", "Competitor", "Total Fare", "Pax Fare", "Vehicle Fare", "Cabin Fare"],
        "rows": [
            {"rank": i, "route": r[0], "source": r[1], "total_fare": _f(r[2]),
             "pax_fare": _f(r[3]), "veh_fare": _f(r[4]), "cab_fare": _f(r[5])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_fjl_comp_fare(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT source,
               ROUND(AVG(total_fare)::numeric, 2) AS avg_total,
               ROUND(AVG(out_per_pax_fare)::numeric, 2) AS avg_pax,
               ROUND(AVG(out_veh_fare)::numeric, 2) AS avg_vehicle,
               ROUND(AVG(out_cab_fare)::numeric, 2) AS avg_cabin
        FROM {view}
        WHERE cap_date = :cap_date
          AND curr_code = :currency
          AND strpos(lower(source), 'fjordline') = 0
        GROUP BY source
        ORDER BY avg_total ASC
    """), {"cap_date": cap_date, "currency": currency}).fetchall()
    return {
        "columns": ["#", "Competitor", "Avg Total", "Avg Pax", "Avg Vehicle", "Avg Cabin"],
        "rows": [
            {"rank": i, "source": r[0], "avg_total": _f(r[1]), "avg_pax": _f(r[2]),
             "avg_vehicle": _f(r[3]), "avg_cabin": _f(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_fjl_dep_dates(db: Session, view: str, cap_date: str, currency: str | None = None) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT out_dep_date,
               COUNT(DISTINCT source) AS competitors,
               COUNT(DISTINCT org || '-' || dest) AS routes
        FROM {view}
        WHERE cap_date = :cap_date
          AND curr_code = :currency
        GROUP BY out_dep_date
        ORDER BY out_dep_date
    """), {"cap_date": cap_date, "currency": currency}).fetchall()
    return {
        "columns": ["#", "Departure Date", "Competitors", "Routes"],
        "rows": [
            {"rank": i,
             "out_dep_date": r[0].isoformat() if r[0] is not None else "",
             "competitors": _i(r[1]), "routes": _i(r[2])}
            for i, r in enumerate(rows, start=1)
        ],
    }


AIRLINE_CFG: dict[str, dict[str, Any]] = {
    "JY": {
        "view": "vw_airline_cpi_jy_snapshot",
        "summary_sql": _summary_sql_jy,
        "meta": _JY_KPI_META,
        "float_keys": _JY_FLOAT_KEYS,
        "null_keys": _JY_NULL_KEYS,
        "details": {
            "airlines_analyzed": _detail_jy_airlines,
            "markets_covered": _detail_jy_markets,
            "jy_avg_fare": _detail_jy_jy_fare,
            "competitors_avg_fare": _detail_jy_comp_fare_by_route,
            "dep_dates_monitored": _detail_jy_dep_dates,
        },
    },
    "PW": {
        "view": "vw_airline_cpi_pw_snapshot",
        "summary_sql": _summary_sql_pw,
        "meta": _PW_KPI_META,
        "float_keys": _PW_FLOAT_KEYS,
        "null_keys": _PW_NULL_KEYS,
        "details": {
            "competitors_analyzed": _detail_pw_competitors,
            "routes_covered": _detail_pw_routes,
            "pw_avg_fare": _detail_pw_pw_fare,
            "competitors_avg_fare": _detail_pw_comp_fare,
            "dep_dates_monitored": _detail_pw_dep_dates,
        },
    },
    "FJL": {
        "view": "vw_cfl_cpi_fjl_snapshot",
        "summary_sql": _summary_sql_fjl,
        "meta": _FJL_KPI_META,
        "float_keys": _FJL_FLOAT_KEYS,
        "details": {
            "competitors_tracked": _detail_fjl_competitors,
            "routes_covered": _detail_fjl_routes,
            "fjl_avg_fare": _detail_fjl_avg_fare,
            "competitors_avg_fare": _detail_fjl_comp_fare,
            "dep_dates_monitored": _detail_fjl_dep_dates,
        },
    },
}


def _resolve_cfg(
    airline_code: str,
    user_identity: str,
    user_roles: list[str],
) -> tuple[str, dict[str, Any]]:
    """Validate + authorize the airline_code, returning (code, config).

    Order matters: reject platform admins and identity mismatches (403)
    before disclosing whether a code is supported (422).
    """
    code = (airline_code or "").upper()

    if is_platform_admin(user_identity, user_roles):
        raise HTTPException(403, detail={
            "message": "Platform administrators do not have access to tenant KPIs.",
        })
    if user_identity != code:
        raise HTTPException(403, detail={
            "message": f"Access denied: KPIs for '{code}' are restricted to {code} users.",
        })

    cfg = AIRLINE_CFG.get(code)
    if not cfg:
        raise HTTPException(422, detail={
            "message": f"KPI breakdown is not available for '{code}'. Supported: {sorted(AIRLINE_CFG)}",
        })
    return code, cfg


# ── Endpoints ───────────────────────────────────────────────

@router.get("/{airline_code}/summary")
def get_kpi_summary(
    airline_code: str,
    cap_date: str = Query(..., description="YYYY-MM-DD"),
    currency: str | None = Query(None, description="FJL only: NOK | EUR | DKK (default NOK)"),
    db: Session = Depends(get_db),
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Return all KPI summary values for one cap_date."""
    code, cfg = _resolve_cfg(airline_code, user_identity, user_roles)
    _validate_cap_date(cap_date)
    resolved_currency = _resolve_currency(code, currency)

    view = cfg["view"]
    meta = cfg["meta"]
    float_keys = cfg["float_keys"]
    null_keys = cfg.get("null_keys", frozenset())
    sql = cfg["summary_sql"](view)
    params: dict[str, Any] = {"cap_date": cap_date}
    if resolved_currency is not None:
        params["currency"] = resolved_currency
    kpis: dict[str, Any] = {}
    try:
        for key, query in sql.items():
            scalar = db.execute(text(query), params).scalar()
            if key in null_keys:
                value = _n_f(scalar) if key in float_keys else _n_i(scalar)
            else:
                value = _f(scalar) if key in float_keys else _i(scalar)
            kpis[key] = {
                "value": value,
                "label": meta[key]["label"],
                "subheader": meta[key]["subheader"],
            }
    except HTTPException:
        raise
    except Exception as e:
        _log.error(f"[kpi] summary query failed ({code}, {cap_date}): {e}")
        raise HTTPException(500, detail={"message": "Could not compute KPI summary"})

    return {
        "cap_date": cap_date,
        "airline_code": code,
        "currency": resolved_currency,
        "kpis": kpis,
    }


@router.get("/{airline_code}/detail/{kpi_key}")
def get_kpi_detail(
    airline_code: str,
    kpi_key: str,
    cap_date: str = Query(..., description="YYYY-MM-DD"),
    currency: str | None = Query(None, description="FJL only: NOK | EUR | DKK (default NOK)"),
    db: Session = Depends(get_db),
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Return the detail table (columns + rows) for one KPI tile."""
    code, cfg = _resolve_cfg(airline_code, user_identity, user_roles)
    builders = cfg["details"]
    if kpi_key not in builders:
        raise HTTPException(422, detail={
            "message": f"Invalid kpi_key '{kpi_key}'. Valid keys: {list(builders)}",
        })
    _validate_cap_date(cap_date)
    resolved_currency = _resolve_currency(code, currency)

    try:
        result = builders[kpi_key](db, cfg["view"], cap_date, resolved_currency)
    except HTTPException:
        raise
    except Exception as e:
        _log.error(f"[kpi] detail query failed ({code}, {kpi_key}, {cap_date}): {e}")
        raise HTTPException(500, detail={"message": "Could not compute KPI detail"})

    return {
        "cap_date": cap_date,
        "airline_code": code,
        "currency": resolved_currency,
        "kpi_key": kpi_key,
        "columns": result["columns"],
        "rows": result["rows"],
    }
