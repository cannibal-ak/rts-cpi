"""Keep the Superset filter-dropdown cache warm so no user pays the cold cost.

Ran by /etc/cron.d/cpi-filter-warm every 4 minutes as:
    docker exec -i cpi-api-1 sh -c 'PYTHONPATH=/app python -' \
        < /opt/cpi/scripts/warm_filter_cache.py >> /var/log/cpi-filter-warm.log 2>&1

Why: the external filter bar's dropdowns each cost a distinct-values query
via Superset's chart-data API. Superset caches results in Redis db3 with a
300s TTL (infra/superset_config.py DATA_CACHE_CONFIG). Without a warmer, the
first page load after every TTL lapse re-ran the queries in the user's face —
measured 2026-08-31 at ~39s for JY's six dropdowns (pre-index; ~5s after the
ix_air_snap_jy_* partial indexes). This script force-refreshes those cache
entries every 4 min (< 300s TTL), so the entry a real page load hits is
always warm, and fresh values appear at most ~4 min after ingestion lands.

Queries run SERIALLY on purpose: one extra pg backend of load, not six.

Filter targets are read live from each dashboard's native-filter config —
the same source the /filter-config endpoint uses — so a filter added or
retargeted in Superset is picked up automatically. Suppressed columns
(hidden_filter_columns in the DASHBOARDS registry) are skipped, matching
what the filter bar actually shows.
"""
import asyncio
import sys
import time

sys.path.insert(0, "/app")

from app.routers.superset import (  # noqa: E402
    DASHBOARDS,
    _filter_target,
    _hidden_filter_columns,
    superset_client,
)

# App-level dashboard ids to keep warm. "1" = JY (interCaribbean), whose
# users reported the slow Latest Prices tab. Add "2" (PW), "5" (WM), "6"/"7"
# (DA/5L) here only after checking their partition has index coverage for
# every filter column — an unindexed tenant makes each cron cycle a stack of
# multi-second seq scans (see ix_air_snap_da_filtervals precedent).
WARM_DASHBOARDS = ["1"]


async def _force_column_values(dataset_id: int, column: str) -> int:
    """Same payload as SupersetClient.fetch_column_values, plus force=True so
    Superset re-runs the query and re-caches the result with a fresh TTL."""
    payload = {
        "datasource": {"id": dataset_id, "type": "table"},
        "queries": [{
            "columns": [column],
            "metrics": [],
            "filters": [],
            "orderby": [],
            "annotation_layers": [],
            "row_limit": 1000,
            "extras": {"having": "", "where": ""},
        }],
        "force": True,
        "result_format": "json",
        "result_type": "results",
    }
    data = await superset_client._session_post("/api/v1/chart/data", payload, timeout=90.0)
    rows = (data.get("result") or [{}])[0].get("data") or []
    return len(rows)


async def main() -> None:
    t_run = time.monotonic()
    parts = []
    failures = 0
    for dash_id in WARM_DASHBOARDS:
        dash = DASHBOARDS[dash_id]
        hidden = _hidden_filter_columns(dash)
        try:
            raw = await superset_client.get_native_filters(dash["superset_id"])
        except Exception as e:
            parts.append("dash %s: filter list failed: %r" % (dash_id, e))
            failures += 1
            continue
        for f in raw:
            if f.get("filterType") != "filter_select":
                continue
            ds_id, column = _filter_target(f)
            if not ds_id or not column or column.lower() in hidden:
                continue
            t = time.monotonic()
            try:
                n = await _force_column_values(ds_id, column)
                parts.append("%s.%s=%d/%.1fs" % (ds_id, column, n, time.monotonic() - t))
            except Exception as e:
                parts.append("%s.%s FAILED %r" % (ds_id, column, e))
                failures += 1
    status = "OK" if failures == 0 else "PARTIAL(%d failed)" % failures
    print("%s warm %s total=%.1fs %s" % (
        time.strftime("%Y-%m-%d %H:%M:%S"), status,
        time.monotonic() - t_run, " ".join(parts),
    ), flush=True)
    sys.exit(1 if failures else 0)


asyncio.run(main())
