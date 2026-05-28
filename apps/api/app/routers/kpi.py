"""KPI summary + detail endpoints for the airline CPI dashboard.

Backs the React click-to-expand KPI row (KPICard / KPIDetailPanel / KPIRow).
Each tenant's KPI summary values AND their per-tile detail tables are computed
here so they stay in sync with each other and respond to the Cap Date picker —
previously the summary tiles were Superset big-number charts.

Scope: JY and PW. Both use the same view schema but expose a *different* set
of KPIs (JY: airlines/markets/cheaper%/undercut; PW: competitors/routes/avg
fares/dep dates), so the KPI keys, SQL, meta and detail builders are kept in a
per-airline registry (AIRLINE_CFG). The cruise/ferry (FJL) view has a different
fare schema entirely and is intentionally not exposed; anything not in the
registry returns 422.

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
        "cheaper_routes_pct": f"""
            WITH route_avg AS (
              SELECT ref_org || '-' || ref_dst AS route,
                     AVG(ref_tot_fare) AS jy_avg,
                     AVG(comp_tot_fare) AS comp_avg
              FROM {view}
              WHERE cap_date = :cap_date
              GROUP BY ref_org || '-' || ref_dst
            )
            SELECT ROUND(
              COUNT(*) FILTER (WHERE jy_avg < comp_avg) * 100.0
              / NULLIF(COUNT(*), 0)
            , 0)
            FROM route_avg
        """,
        "undercut_count": f"""
            WITH route_comp_avg AS (
              SELECT ref_org || '-' || ref_dst AS route, comp_al,
                     AVG(ref_tot_fare) AS jy_avg,
                     AVG(comp_tot_fare) AS comp_avg
              FROM {view}
              WHERE cap_date = :cap_date
              GROUP BY ref_org || '-' || ref_dst, comp_al
            )
            SELECT COUNT(*)
            FROM route_comp_avg
            WHERE comp_avg < jy_avg
        """,
    }


_JY_KPI_META = {
    "airlines_analyzed": {"label": "Airlines Analyzed", "subheader": "Distinct competitors tracked"},
    "markets_covered":   {"label": "Markets Covered", "subheader": "Origin-destination pairs analyzed"},
    "cheaper_routes_pct": {"label": "Cheaper on Routes %", "subheader": "Routes where JY is cheaper"},
    "undercut_count":    {"label": "Undercut Count", "subheader": "Route-competitor pairs beating JY"},
}


def _detail_jy_airlines(db: Session, view: str, cap_date: str) -> dict[str, Any]:
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


def _detail_jy_markets(db: Session, view: str, cap_date: str) -> dict[str, Any]:
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


def _detail_jy_cheaper(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_org || ' → ' || ref_dst AS route,
               ROUND(AVG(ref_tot_fare)::numeric, 0) AS jy_avg,
               ROUND(AVG(comp_tot_fare)::numeric, 0) AS comp_avg,
               ROUND((AVG(ref_tot_fare) - AVG(comp_tot_fare))::numeric, 0) AS delta,
               CASE WHEN AVG(ref_tot_fare) < AVG(comp_tot_fare)
                    THEN 'JY' ELSE 'Comp' END AS winner
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_org, ref_dst
        ORDER BY delta ASC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["Route", "JY avg", "Comp avg", "Δ", "Winner"],
        "rows": [
            {"route": r[0], "jy_avg": _i(r[1]), "comp_avg": _i(r[2]),
             "delta": _i(r[3]), "winner": r[4]}
            for r in rows
        ],
    }


def _detail_jy_undercut(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_org || ' → ' || ref_dst AS route,
               comp_al,
               ROUND(AVG(ref_tot_fare)::numeric, 0) AS jy_avg,
               ROUND(AVG(comp_tot_fare)::numeric, 0) AS comp_avg,
               ROUND((AVG(comp_tot_fare) - AVG(ref_tot_fare))::numeric, 0) AS gap
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_org, ref_dst, comp_al
        HAVING AVG(comp_tot_fare) < AVG(ref_tot_fare)
        ORDER BY gap ASC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["Route", "Competitor", "JY avg", "Comp avg", "Gap"],
        "rows": [
            {"route": r[0], "comp_al": r[1], "jy_avg": _i(r[2]),
             "comp_avg": _i(r[3]), "gap": _i(r[4])}
            for r in rows
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
            SELECT ROUND(AVG(ref_tot_fare)::numeric, 2)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "competitors_avg_fare": f"""
            SELECT ROUND(AVG(comp_tot_fare)::numeric, 2)
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


def _detail_pw_competitors(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT comp_al,
               COUNT(DISTINCT ref_org || '-' || ref_dst) AS routes,
               ROUND(AVG(comp_tot_fare)::numeric, 0) AS avg_fare,
               ROUND((AVG(comp_tot_fare) - AVG(ref_tot_fare))::numeric, 0) AS fare_gap
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY comp_al
        ORDER BY routes DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Competitor", "Routes", "Avg Fare", "Fare Gap"],
        "rows": [
            {"rank": i, "comp_al": r[0], "routes": _i(r[1]),
             "avg_fare": _i(r[2]), "fare_gap": _i(r[3])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_pw_routes(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_org || ' → ' || ref_dst AS route,
               COUNT(DISTINCT comp_al) AS competitors,
               ROUND(AVG(ref_tot_fare)::numeric, 0) AS pw_avg,
               ROUND(AVG(comp_tot_fare)::numeric, 0) AS comp_avg,
               ROUND((AVG(comp_tot_fare) - AVG(ref_tot_fare))::numeric, 0) AS fare_gap
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_org, ref_dst
        ORDER BY competitors DESC, route
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Route", "Competitors", "PW Avg Fare", "Comp Avg Fare", "Fare Gap"],
        "rows": [
            {"rank": i, "route": r[0], "competitors": _i(r[1]),
             "pw_avg": _i(r[2]), "comp_avg": _i(r[3]), "fare_gap": _i(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_pw_pw_fare(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_org || ' → ' || ref_dst AS route,
               ROUND(AVG(ref_tot_fare)::numeric, 0) AS avg_fare,
               ROUND(MIN(ref_tot_fare)::numeric, 0) AS min_fare,
               ROUND(MAX(ref_tot_fare)::numeric, 0) AS max_fare,
               COUNT(*) AS records
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_org, ref_dst
        ORDER BY avg_fare DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Route", "PW Avg Fare", "Min Fare", "Max Fare", "Records"],
        "rows": [
            {"rank": i, "route": r[0], "avg_fare": _i(r[1]),
             "min_fare": _i(r[2]), "max_fare": _i(r[3]), "records": _i(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_pw_comp_fare(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT comp_al,
               ROUND(AVG(comp_tot_fare)::numeric, 0) AS avg_fare,
               ROUND(MIN(comp_tot_fare)::numeric, 0) AS min_fare,
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
            {"rank": i, "comp_al": r[0], "avg_fare": _i(r[1]),
             "min_fare": _i(r[2]), "max_fare": _i(r[3]), "routes": _i(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_pw_dep_dates(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT ref_dep_date,
               COUNT(*) AS records,
               COUNT(DISTINCT comp_al) AS competitors,
               COUNT(DISTINCT ref_org || '-' || ref_dst) AS routes
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY ref_dep_date
        ORDER BY ref_dep_date DESC
        LIMIT 50
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Dep Date", "Records", "Competitors", "Routes"],
        "rows": [
            {"rank": i,
             "ref_dep_date": r[0].isoformat() if r[0] is not None else "",
             "records": _i(r[1]), "competitors": _i(r[2]), "routes": _i(r[3])}
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
# NOTE: total_fare blends currencies (EUR/DKK/NOK) across sources, so the fare
# averages are intentionally currency-mixed, mirroring the raw data.


def _summary_sql_fjl(view: str) -> dict[str, str]:
    return {
        "competitors_tracked": f"""
            SELECT COUNT(DISTINCT source)
            FROM {view}
            WHERE cap_date = :cap_date
              AND strpos(lower(source), 'fjordline') = 0
        """,
        "routes_covered": f"""
            SELECT COUNT(DISTINCT org || '-' || dest)
            FROM {view}
            WHERE cap_date = :cap_date
        """,
        "fjl_avg_fare": f"""
            SELECT ROUND(AVG(total_fare)::numeric, 2)
            FROM {view}
            WHERE cap_date = :cap_date
              AND strpos(lower(source), 'fjordline') > 0
        """,
        "competitors_avg_fare": f"""
            SELECT ROUND(AVG(total_fare)::numeric, 2)
            FROM {view}
            WHERE cap_date = :cap_date
              AND strpos(lower(source), 'fjordline') = 0
        """,
        "dep_dates_monitored": f"""
            SELECT COUNT(DISTINCT out_dep_date)
            FROM {view}
            WHERE cap_date = :cap_date
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


def _detail_fjl_competitors(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT source,
               COUNT(DISTINCT org || '-' || dest) AS routes,
               ROUND(AVG(total_fare)::numeric, 2) AS avg_total,
               ROUND(AVG(out_per_pax_fare)::numeric, 2) AS avg_pax,
               COUNT(*) AS records
        FROM {view}
        WHERE cap_date = :cap_date
          AND strpos(lower(source), 'fjordline') = 0
        GROUP BY source
        ORDER BY avg_total DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Competitor", "Routes", "Avg Total Fare", "Avg Pax Fare", "Records"],
        "rows": [
            {"rank": i, "source": r[0], "routes": _i(r[1]),
             "avg_total": _f(r[2]), "avg_pax": _f(r[3]), "records": _i(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_fjl_routes(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT org || ' → ' || dest AS route,
               COUNT(DISTINCT source) AS competitors,
               ROUND(AVG(total_fare)::numeric, 2) AS avg_fare,
               ROUND(MIN(total_fare)::numeric, 2) AS min_fare,
               ROUND(MAX(total_fare)::numeric, 2) AS max_fare
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY org, dest
        ORDER BY avg_fare DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Route", "Competitors", "Avg Fare", "Min Fare", "Max Fare"],
        "rows": [
            {"rank": i, "route": r[0], "competitors": _i(r[1]),
             "avg_fare": _f(r[2]), "min_fare": _f(r[3]), "max_fare": _f(r[4])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_fjl_avg_fare(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT org || ' → ' || dest AS route,
               source,
               ROUND(AVG(total_fare)::numeric, 2) AS total_fare,
               ROUND(AVG(out_per_pax_fare)::numeric, 2) AS pax_fare,
               ROUND(AVG(out_veh_fare)::numeric, 2) AS veh_fare,
               ROUND(AVG(out_cab_fare)::numeric, 2) AS cab_fare
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY org, dest, source
        ORDER BY total_fare DESC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Route", "Competitor", "Total Fare", "Pax Fare", "Vehicle Fare", "Cabin Fare"],
        "rows": [
            {"rank": i, "route": r[0], "source": r[1], "total_fare": _f(r[2]),
             "pax_fare": _f(r[3]), "veh_fare": _f(r[4]), "cab_fare": _f(r[5])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_fjl_comp_fare(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT source,
               ROUND(AVG(total_fare)::numeric, 2) AS avg_total,
               ROUND(AVG(out_per_pax_fare)::numeric, 2) AS avg_pax,
               ROUND(AVG(out_veh_fare)::numeric, 2) AS avg_vehicle,
               ROUND(AVG(out_cab_fare)::numeric, 2) AS avg_cabin,
               COUNT(*) AS records
        FROM {view}
        WHERE cap_date = :cap_date
          AND strpos(lower(source), 'fjordline') = 0
        GROUP BY source
        ORDER BY avg_total ASC
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Competitor", "Avg Total", "Avg Pax", "Avg Vehicle", "Avg Cabin", "Records"],
        "rows": [
            {"rank": i, "source": r[0], "avg_total": _f(r[1]), "avg_pax": _f(r[2]),
             "avg_vehicle": _f(r[3]), "avg_cabin": _f(r[4]), "records": _i(r[5])}
            for i, r in enumerate(rows, start=1)
        ],
    }


def _detail_fjl_dep_dates(db: Session, view: str, cap_date: str) -> dict[str, Any]:
    rows = db.execute(text(f"""
        SELECT out_dep_date,
               COUNT(*) AS records,
               COUNT(DISTINCT source) AS competitors,
               COUNT(DISTINCT org || '-' || dest) AS routes
        FROM {view}
        WHERE cap_date = :cap_date
        GROUP BY out_dep_date
        ORDER BY out_dep_date
    """), {"cap_date": cap_date}).fetchall()
    return {
        "columns": ["#", "Departure Date", "Records", "Competitors", "Routes"],
        "rows": [
            {"rank": i,
             "out_dep_date": r[0].isoformat() if r[0] is not None else "",
             "records": _i(r[1]), "competitors": _i(r[2]), "routes": _i(r[3])}
            for i, r in enumerate(rows, start=1)
        ],
    }


AIRLINE_CFG: dict[str, dict[str, Any]] = {
    "JY": {
        "view": "vw_airline_cpi_jy_snapshot",
        "summary_sql": _summary_sql_jy,
        "meta": _JY_KPI_META,
        "float_keys": frozenset(),
        "details": {
            "airlines_analyzed": _detail_jy_airlines,
            "markets_covered": _detail_jy_markets,
            "cheaper_routes_pct": _detail_jy_cheaper,
            "undercut_count": _detail_jy_undercut,
        },
    },
    "PW": {
        "view": "vw_airline_cpi_pw_snapshot",
        "summary_sql": _summary_sql_pw,
        "meta": _PW_KPI_META,
        "float_keys": _PW_FLOAT_KEYS,
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
    db: Session = Depends(get_db),
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Return all KPI summary values for one cap_date."""
    code, cfg = _resolve_cfg(airline_code, user_identity, user_roles)
    _validate_cap_date(cap_date)

    view = cfg["view"]
    meta = cfg["meta"]
    float_keys = cfg["float_keys"]
    sql = cfg["summary_sql"](view)
    kpis: dict[str, Any] = {}
    try:
        for key, query in sql.items():
            scalar = db.execute(text(query), {"cap_date": cap_date}).scalar()
            kpis[key] = {
                "value": _f(scalar) if key in float_keys else _i(scalar),
                "label": meta[key]["label"],
                "subheader": meta[key]["subheader"],
            }
    except HTTPException:
        raise
    except Exception as e:
        _log.error(f"[kpi] summary query failed ({code}, {cap_date}): {e}")
        raise HTTPException(500, detail={"message": "Could not compute KPI summary"})

    return {"cap_date": cap_date, "airline_code": code, "kpis": kpis}


@router.get("/{airline_code}/detail/{kpi_key}")
def get_kpi_detail(
    airline_code: str,
    kpi_key: str,
    cap_date: str = Query(..., description="YYYY-MM-DD"),
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

    try:
        result = builders[kpi_key](db, cfg["view"], cap_date)
    except HTTPException:
        raise
    except Exception as e:
        _log.error(f"[kpi] detail query failed ({code}, {kpi_key}, {cap_date}): {e}")
        raise HTTPException(500, detail={"message": "Could not compute KPI detail"})

    return {
        "cap_date": cap_date,
        "airline_code": code,
        "kpi_key": kpi_key,
        "columns": result["columns"],
        "rows": result["rows"],
    }
