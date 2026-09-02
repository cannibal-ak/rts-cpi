"""Alert endpoints — tenant-scoped feed, per-user read state, preset settings.

    GET    /api/v1/alerts/events               list, paginated + filtered
    GET    /api/v1/alerts/summary              unread count + 5 most recent
    GET    /api/v1/alerts/events/unread-count  just the badge number
    POST   /api/v1/alerts/events/read          mark specific events read
    POST   /api/v1/alerts/events/unread        mark them unread again
    POST   /api/v1/alerts/events/read-all      mark everything read
    GET    /api/v1/alerts/rules                catalogue presets + user instances
    GET    /api/v1/alerts/rules/{rule_key}
    PATCH  /api/v1/alerts/rules/{rule_key}     TENANT_ADMIN
    POST   /api/v1/alerts/rules/{rule_key}/preview   TENANT_ADMIN
    POST   /api/v1/alerts/rules                TENANT_ADMIN — create an instance
    DELETE /api/v1/alerts/rules/{rule_key}     TENANT_ADMIN — any rule
    POST   /api/v1/alerts/rules/{rule_key}/restore  TENANT_ADMIN — built-ins
    POST   /api/v1/alerts/run                  TENANT_ADMIN

AUTH MODEL. Reading and marking-read are personal actions, open to any
authenticated user of the tenant. Editing a rule changes what every user in the
tenant sees, so it takes TENANT_ADMIN — applied per-route, not at the router, so
the read paths stay open. `get_tenant_db` scopes rows but does NOT check roles;
the role dependency is what does that.

This makes /alerts/rules the first tenant-admin-owned settings surface in the
app — every existing /admin/* route is RTS platform admin only.
"""

import json
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.cache import cached
from app.core.database import set_tenant_context
from app.core.deps import (
    RequireRoles, get_current_user, get_tenant_db, get_tenant_id,
    get_user_identity, sanitize_date, sanitize_filter,
)
from app.schemas.alerts import (
    AlertEventOut, AlertPreviewOut, AlertPreviewRow, AlertRuleCreate,
    AlertRuleOut, AlertRuleUpdate, AlertRunSummaryOut, AlertSummaryOut,
    MarkAllReadIn, MarkReadIn, MarkReadOut, TunableFieldOut,
)
from app.schemas.common import PageInfo, PaginatedResponse
from app.services.alerts import evaluator, read_state, runner
from app.services.alerts.presets import (
    windows_for_horizon,
    PRESETS, PRESET_ORDER, get_preset, missing_requirements, tunables_payload,
)
from app.services.alerts.views import is_alertable, resolve_view

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

_ADMIN = Depends(RequireRoles("TENANT_ADMIN"))

# The list query's columns. `is_read` is an anti-join against the caller's own
# receipts, so two users of the same tenant see the same events with different
# read state.
_EVENT_SELECT = """
    SELECT e.id, e.rule_id, e.rule_key, e.rule_name, e.triggered_at,
           e.severity, e.message, e.delivery_status, e.scope_key,
           e.observed_at, e.prev_observed_at, e.evaluation_mode, e.payload,
           (r.id IS NOT NULL) AS is_read
      FROM alert_event e
      LEFT JOIN alert_event_read r
             ON r.event_id = e.id AND r.user_id = CAST(:uid AS uuid)
"""


def _commit(db: Session, tenant_id: str) -> None:
    """Commit, then re-establish the RLS tenant context.

    `set_tenant_context` issues SET LOCAL, which is scoped to the transaction.
    `get_tenant_db` sets it once when the request opens, so the FIRST commit
    inside a handler silently drops it and every subsequent read in that same
    request is filtered to nothing — a mark-read call would report the tenant's
    unread count as 0 rather than one fewer. Anything that commits and then
    reads must go through here.
    """
    db.commit()
    set_tenant_context(db, tenant_id)


def _user_id(current_user: dict) -> str:
    uid = current_user.get("sub")
    if not uid:
        raise HTTPException(401, "token carries no subject")
    return str(uid)


def _row_to_event(r) -> AlertEventOut:
    return AlertEventOut(
        id=r.id, rule_id=r.rule_id, rule_key=r.rule_key, rule_name=r.rule_name,
        triggered_at=r.triggered_at, severity=r.severity, message=r.message,
        delivery_status=r.delivery_status, scope_key=r.scope_key,
        observed_at=r.observed_at, prev_observed_at=r.prev_observed_at,
        evaluation_mode=r.evaluation_mode, payload=r.payload or {},
        is_read=bool(r.is_read),
    )


# ─────────────────────────────────────────────────────────────
# Feed
# ─────────────────────────────────────────────────────────────

@router.get("/events", response_model=PaginatedResponse[AlertEventOut])
def list_events(
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    unread_only: bool = Query(False),
    rule_key: str | None = Query(None),
    severity: str | None = Query(None, pattern="^(info|warning|critical)$"),
    route: str | None = Query(None),
    competitor: str | None = Query(None),
    since: str | None = Query(None, description="observed_at >= YYYY-MM-DD"),
    until: str | None = Query(None, description="observed_at <= YYYY-MM-DD"),
    with_total: bool = Query(True),
):
    uid = _user_id(current_user)
    route = sanitize_filter(route, "route")
    competitor = sanitize_filter(competitor, "competitor")
    rule_key = sanitize_filter(rule_key, "rule_key")
    since = sanitize_date(since, "since")
    until = sanitize_date(until, "until")

    # Rows written purely to keep the position rules' state ledger honest
    # (a muted recovery) are records, not notifications.
    where, params = ["e.delivery_status <> 'suppressed'"], {"uid": uid}
    if unread_only:
        where.append("r.id IS NULL")
    if rule_key:
        where.append("e.rule_key = :rule_key")
        params["rule_key"] = rule_key
    if severity:
        where.append("e.severity = :severity")
        params["severity"] = severity
    # Containment (@>), not ->>. ix_alert_event_payload_gin is jsonb_path_ops,
    # which indexes @> / @? / @@ and can NEVER serve a ->> text comparison -
    # written the other way these two filters sequentially scanned the table
    # while the index built for them sat unread. The value is still bound, so
    # this is no less parameterised than the original.
    if route:
        where.append("e.payload @> CAST(:route_json AS jsonb)")
        params["route_json"] = json.dumps({"route": route})
    if competitor:
        where.append("e.payload @> CAST(:competitor_json AS jsonb)")
        params["competitor_json"] = json.dumps({"competitor": competitor})
    if since:
        where.append("e.observed_at >= CAST(:since AS date)")
        params["since"] = since
    if until:
        where.append("e.observed_at <= CAST(:until AS date)")
        params["until"] = until
    clause = " AND ".join(where)

    total = 0
    if with_total:
        total = db.execute(
            text(f"""
                SELECT count(*) FROM alert_event e
                  LEFT JOIN alert_event_read r
                         ON r.event_id = e.id AND r.user_id = CAST(:uid AS uuid)
                 WHERE {clause}
            """),
            params,
        ).scalar() or 0

    # The id tiebreak is load-bearing, not cosmetic: backfilled events share a
    # triggered_at per capture date, so ordering on the timestamp alone lets
    # rows shuffle between pages and get skipped or repeated.
    rows = db.execute(
        text(f"""
            {_EVENT_SELECT}
             WHERE {clause}
             ORDER BY e.triggered_at DESC, e.id DESC
             LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PaginatedResponse(
        items=[_row_to_event(r) for r in rows],
        page_info=PageInfo(
            total=total, page=page, page_size=page_size,
            has_next=(len(rows) == page_size)
            if not with_total else ((page - 1) * page_size + page_size) < total,
        ),
    )


@router.get("/summary", response_model=AlertSummaryOut)
def summary(
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(5, ge=1, le=20),
):
    """Everything the notification bell needs, in one request.

    The bell polls this once a minute and the popover renders `recent` from it,
    so opening the popover costs nothing and the badge and the list can never
    disagree with each other.
    """
    uid = _user_id(current_user)
    counts = read_state.unread_count(db, uid)
    rows = db.execute(
        text(f"{_EVENT_SELECT} WHERE e.delivery_status <> 'suppressed' "
             f"ORDER BY e.triggered_at DESC, e.id DESC LIMIT :lim"),
        {"uid": uid, "lim": limit},
    ).all()
    newest = db.execute(text(
        "SELECT max(triggered_at) FROM alert_event "
        "WHERE delivery_status <> 'suppressed'")).scalar()
    return AlertSummaryOut(
        unread_count=counts["unread"], capped=counts["capped"],
        recent=[_row_to_event(r) for r in rows], newest_triggered_at=newest,
    )


@router.get("/events/unread-count")
def unread_count(
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    return read_state.unread_count(db, _user_id(current_user))


# How long a tenant's route list may be served from memory. The same 300s the
# airline filter-metadata endpoint uses: routes change once per daily ingest,
# so even five minutes of staleness only delays a NEW route's appearance.
_ROUTES_TTL = 300.0


def _available_options(db: Session, identity: str) -> dict[str, list[str]]:
    """Tenant DATA that fills the settings multiselects: routes and carriers.

    ONE producer, deliberately, not one per picker. The first statement here is
    `SELECT max(cap_date) FROM {view}`, which costs 0.062 ms on DA but 769 ms on
    JY and 818 ms on PW: those partitions have no ix_air_snap_<tenant>_grid, so
    it degenerates into a full scan of the whole table. A second producer would
    double the settings page's cold-miss cost on exactly the tenants that can
    least afford it.

    Same union rule as the routes list always had — what is in the latest
    capture, plus anything an event has already fired for, so an old alert's
    route or carrier stays pickable after it leaves the feed. Cached per
    identity, which is also what resolves the view, so the cache can never hand
    one tenant another tenant's data.
    """
    view = resolve_view(identity)

    def _produce() -> dict[str, list[str]]:
        routes: set[str] = set()
        comps: set[str] = set()
        horizon: int | None = None
        cap = db.execute(text(f"SELECT max(cap_date) FROM {view}")).scalar()
        if cap is not None:
            rows = db.execute(
                text(f"SELECT DISTINCT ref_org || '-' || ref_dst AS route,"
                     f"       comp_al"
                     f"  FROM {view} WHERE cap_date = :cap"),
                {"cap": cap},
            ).all()
            routes.update(r.route for r in rows if r.route)
            comps.update(r.comp_al for r in rows if r.comp_al)
            # How far ahead this feed quotes, which decides which departure
            # buckets the tenant can actually populate. Read from the same
            # pinned capture as the rest, so it costs no extra scan: DA, PW and
            # ALT come back 29 and see three buckets; JY and 5L 45 and see
            # four; WM 85 and sees all six.
            horizon = db.execute(
                text(f"SELECT max(ref_dep_date - cap_date) FROM {view}"
                     f" WHERE cap_date = :cap"),
                {"cap": cap},
            ).scalar()
        rows = db.execute(text(
            "SELECT DISTINCT payload->>'route' AS route,"
            "       payload->>'competitor' AS competitor"
            "  FROM alert_event")).all()
        routes.update(r.route for r in rows if r.route)
        comps.update(r.competitor for r in rows if r.competitor)
        # Sorted because the Autocomplete renders them in the order given —
        # except windows, which are already in ladder order and must stay that
        # way: "00-07, 08-14, 15-30" reads as a horizon, sorted() would too but
        # only by accident of the zero padding.
        return {
            "routes": sorted(routes),
            "competitors": sorted(comps),
            "windows": windows_for_horizon(horizon),
        }

    return cached(("alert_options", identity), _ROUTES_TTL, _produce)


def _available_routes(db: Session, identity: str) -> list[str]:
    """Every ORG-DST route the tenant can meaningfully filter alerts by.

    Union of two sets: the routes in the LATEST capture of the tenant's fare
    view (what "available in the application" means to a user), plus every
    route an event has already fired for — an old alert's route stays
    pickable after the route leaves the feed. The cap_date equality pin is
    the queries.py invariant: unpinned, the DISTINCT walks the whole
    multi-million-row view; pinned, it rides the tenant's grid index. The
    events pass filters on payload text rather than @> because it WANTS the
    tiny seq scan — the gin jsonb_path_ops index cannot serve ->> anyway.

    Cached per identity, which is also what resolves the view — so the cache
    can never hand one tenant another tenant's routes.
    """
    return _available_options(db, identity)["routes"]


@router.get("/routes", response_model=list[str])
def list_routes(
    db: Session = Depends(get_tenant_db),
    user_identity: str = Depends(get_user_identity),
):
    """The Route dropdown's options, in the events filter's exact ORG-DST form.

    Empty (not 400) for identities without an alertable view: the page is
    gated to alert tenants anyway, and a platform admin poking the endpoint
    should see "no routes", not an error.
    """
    if not is_alertable(user_identity):
        return []
    return _available_routes(db, user_identity)


@router.post("/events/read", response_model=MarkReadOut)
def mark_read(
    body: MarkReadIn,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    uid = _user_id(current_user)
    updated = read_state.mark_read(
        db, tenant_id, uid, [str(i) for i in body.event_ids])
    _commit(db, tenant_id)
    return MarkReadOut(updated=updated,
                       unread_count=read_state.unread_count(db, uid)["unread"])


# POST rather than DELETE-with-body: a request body on DELETE is legal but
# poorly supported — proxies and some fetch stacks drop it — and the shared
# `del()` helper in the frontend http client deliberately takes no body.
@router.post("/events/unread", response_model=MarkReadOut)
def mark_unread(
    body: MarkReadIn,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    uid = _user_id(current_user)
    updated = read_state.mark_unread(db, uid, [str(i) for i in body.event_ids])
    _commit(db, tenant_id)
    return MarkReadOut(updated=updated,
                       unread_count=read_state.unread_count(db, uid)["unread"])


@router.post("/events/read-all", response_model=MarkReadOut)
def mark_all_read(
    body: MarkAllReadIn | None = None,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id),
):
    uid = _user_id(current_user)
    before = body.before.isoformat() if body and body.before else None
    updated = read_state.mark_all_read(db, uid, before)
    _commit(db, tenant_id)
    return MarkReadOut(updated=updated,
                       unread_count=read_state.unread_count(db, uid)["unread"])


# ─────────────────────────────────────────────────────────────
# Rules
# ─────────────────────────────────────────────────────────────

def _rule_out(row, preset, options: dict[str, list[str]] | None = None) -> AlertRuleOut:
    condition = row.condition_json if isinstance(row.condition_json, dict) else {}
    tunables = tunables_payload(preset) if preset else []
    if options is not None and preset is not None:
        # A tenant-data multiselect ships with options=None in the preset —
        # which routes and carriers exist is DATA, not preset shape — and is
        # filled per request from the same cached lists GET /routes serves, so
        # the settings screen and the feed's dropdown can never disagree.
        #
        # Keyed off Tunable.options_source rather than the tunable's name. The
        # name test this replaced only ever matched "routes", which is why the
        # competitors picker declared on two presets has never once rendered:
        # the settings card hides any multiselect whose option list is empty.
        source = {t.key: t.options_source for t in preset.tunables}
        for t in tunables:
            src = source.get(t["key"])
            if src and t["options"] is None:
                t["options"] = options.get(src, [])
    return AlertRuleOut(
        id=row.id, rule_key=row.rule_key, preset_key=row.preset_key,
        name=row.name,
        description=row.description, domain=row.domain, rule_type=row.rule_type,
        is_active=row.is_active, is_preset=row.is_preset,
        severity_default=row.severity_default, condition=condition,
        tunables=[TunableFieldOut(**t) for t in tunables],
        missing_requirements=missing_requirements(preset, condition) if preset else [],
        created_at=row.created_at, updated_at=row.updated_at,
        deleted_at=getattr(row, "deleted_at", None),
        updated_by=getattr(row, "updated_by", None),
    )


_RULE_SELECT = """
    SELECT r.id, r.rule_key, r.preset_key, r.name, r.description, r.domain,
           r.rule_type, r.is_active, r.is_preset, r.severity_default,
           r.condition_json, r.created_at, r.updated_at, r.deleted_at,
           u.email AS updated_by
      FROM alert_rule r
      LEFT JOIN app_user u ON u.id = r.updated_by_user_id
"""


def _ensure_presets(db: Session, tenant_id: str) -> None:
    """Insert any preset row this tenant is missing.

    Self-healing rather than 404, so a tenant onboarded after migration 040 gets
    the catalogue the first time anyone opens the settings screen instead of
    needing a backfill migration of its own.
    """
    existing = set(db.execute(
        text("SELECT rule_key FROM alert_rule WHERE tenant_id = CAST(:t AS uuid)"),
        {"t": tenant_id},
    ).scalars().all())
    import json
    for key in PRESET_ORDER:
        if key in existing:
            continue
        p = PRESETS[key]
        db.execute(
            text("""
                INSERT INTO alert_rule (
                    tenant_id, name, description, domain, rule_type,
                    condition_json, is_active, owner, rule_key, is_preset,
                    preset_key, severity_default
                ) VALUES (
                    CAST(:t AS uuid), :name, :desc, :domain, :rtype,
                    CAST(:cond AS jsonb), :active, 'system', :key, true,
                    :key, :sev
                )
                ON CONFLICT (tenant_id, rule_key) DO NOTHING
            """),
            {"t": tenant_id, "name": p.name, "desc": p.description,
             "domain": p.domain, "rtype": p.rule_type,
             "cond": json.dumps(p.defaults()), "active": p.default_active,
             "key": p.rule_key, "sev": p.severity_default},
        )
    _commit(db, tenant_id)


@router.get("/rules", response_model=list[AlertRuleOut])
def list_rules(
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
    user_identity: str = Depends(get_user_identity),
):
    _ensure_presets(db, tenant_id)
    rows = db.execute(text(f"{_RULE_SELECT} ORDER BY r.is_preset DESC, r.name")).all()
    # Presets first in catalogue order — the shape existing tenants already
    # see — then user instances grouped under the same family order, oldest
    # first, so a new rule lands in a predictable place.
    order = {k: i for i, k in enumerate(PRESET_ORDER)}
    rows = sorted(rows, key=lambda r: (
        0 if r.is_preset else 1,
        order.get(r.preset_key or r.rule_key, 99),
        r.created_at.timestamp() if r.created_at else 0.0,
    ))
    options = _available_options(db, user_identity) if is_alertable(user_identity) else None
    return [_rule_out(r, get_preset(r.preset_key), options) for r in rows]


@router.get("/rules/{rule_key}", response_model=AlertRuleOut)
def get_rule(
    rule_key: str,
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
    user_identity: str = Depends(get_user_identity),
):
    _ensure_presets(db, tenant_id)
    row = db.execute(text(f"{_RULE_SELECT} WHERE r.rule_key = :k"),
                     {"k": rule_key}).first()
    if row is None:
        raise HTTPException(404, f"no rule {rule_key}")
    options = _available_options(db, user_identity) if is_alertable(user_identity) else None
    return _rule_out(row, get_preset(row.preset_key), options)


@router.patch("/rules/{rule_key}", response_model=AlertRuleOut,
              dependencies=[_ADMIN])
def update_rule(
    rule_key: str,
    body: AlertRuleUpdate,
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
    current_user: dict = Depends(get_current_user),
    user_identity: str = Depends(get_user_identity),
):
    import json

    _ensure_presets(db, tenant_id)
    row = db.execute(text(f"{_RULE_SELECT} WHERE r.rule_key = :k"),
                     {"k": rule_key}).first()
    if row is None:
        raise HTTPException(404, f"no rule {rule_key}")
    if row.deleted_at is not None:
        raise HTTPException(400, f"{rule_key} is deleted; restore it before editing")
    preset = get_preset(row.preset_key)
    if preset is None:
        # Legacy free-form rows: no catalogue type, nothing to validate against.
        raise HTTPException(400, f"{rule_key} has no catalogue rule type and cannot be edited")

    name = None
    if body.name is not None:
        if row.is_preset:
            raise HTTPException(400, "built-in rules cannot be renamed")
        name = body.name.strip()
        if not name:
            raise HTTPException(422, detail={
                "message": "invalid name",
                "errors": [{"field": "name", "error": "name cannot be blank"}],
            })

    stored = row.condition_json if isinstance(row.condition_json, dict) else {}
    merged = {**stored, **(body.condition or {})}
    try:
        # Validate the MERGED WHOLE, not just the submitted keys — a patch that
        # is individually valid can still leave the condition inconsistent.
        condition = preset.validate_condition(merged)
    except ValidationError as exc:
        raise HTTPException(422, detail={
            "message": "invalid condition",
            "errors": [
                {"field": ".".join(str(p) for p in e["loc"]), "error": e["msg"]}
                for e in exc.errors()
            ],
        })

    is_active = row.is_active if body.is_active is None else body.is_active
    if is_active:
        missing = missing_requirements(preset, condition)
        if missing:
            raise HTTPException(422, detail={
                "message": (
                    f"{preset.name} needs {', '.join(missing)} before it can be "
                    f"switched on - without it the rule would match every route."
                ),
                "missing": missing,
            })

    db.execute(
        text("""
            UPDATE alert_rule
               SET condition_json = CAST(:cond AS jsonb),
                   is_active = :active,
                   name = COALESCE(:name, name),
                   updated_at = now(),
                   updated_by_user_id = CAST(:uid AS uuid)
             WHERE rule_key = :k
        """),
        {"cond": json.dumps(condition), "active": is_active, "name": name,
         "uid": _user_id(current_user), "k": rule_key},
    )
    _commit(db, tenant_id)
    logger.info(
        "ALERT_RULE_UPDATED actor=%s rule_key=%s active=%s renamed=%s changed=%s",
        current_user.get("email"), rule_key, is_active, name is not None,
        sorted((body.condition or {}).keys()),
    )
    row = db.execute(text(f"{_RULE_SELECT} WHERE r.rule_key = :k"),
                     {"k": rule_key}).first()
    # Same options injection as the GET paths: the settings screen replaces
    # its card state with THIS response, so serving options=None here would
    # blank the routes picker after every save.
    options = _available_options(db, user_identity) if is_alertable(user_identity) else None
    return _rule_out(row, preset, options)


@router.post("/rules/{rule_key}/preview", response_model=AlertPreviewOut,
             dependencies=[_ADMIN])
def preview_rule(
    rule_key: str,
    body: AlertRuleUpdate,
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
    user_identity: str = Depends(get_user_identity),
):
    """What this condition WOULD fire on the newest capture pair. Writes nothing."""
    if not is_alertable(user_identity):
        raise HTTPException(400, f"alerting is not available for {user_identity}")

    # Resolve the row FIRST: for an instance the family comes from its
    # preset_key, not the URL. A bare family key with no row yet (a preset the
    # self-heal has not materialised) still previews against its defaults.
    row = db.execute(text(f"{_RULE_SELECT} WHERE r.rule_key = :k"),
                     {"k": rule_key}).first()
    preset = get_preset(row.preset_key) if row is not None else get_preset(rule_key)
    if preset is None:
        raise HTTPException(404, f"no preset {rule_key}")

    stored = (row.condition_json if row is not None
              and isinstance(row.condition_json, dict) else preset.defaults())
    try:
        condition = preset.validate_condition({**stored, **(body.condition or {})})
    except ValidationError as exc:
        raise HTTPException(422, detail={"message": "invalid condition",
                                         "errors": exc.errors()})

    evaluator.prepare_session(db)
    summary = evaluator.preview_rule(
        db, tenant_id, user_identity, rule_key, condition,
        rule_id=str(row.id) if row else "00000000-0000-0000-0000-000000000000",
        rule_name=row.name if row is not None else preset.name,
        severity=preset.severity_default,
        preset_key=row.preset_key if row is not None else rule_key,
    )
    db.rollback()
    return AlertPreviewOut(
        rule_key=rule_key,
        cap_date=summary.cap_date.isoformat() if summary.cap_date else None,
        prev_cap_date=(summary.prev_cap_date.isoformat()
                       if summary.prev_cap_date else None),
        would_fire=summary.events_created,
        groups_evaluated=summary.groups_evaluated,
        sample=[AlertPreviewRow(**s) for s in summary.samples],
    )


# ─────────────────────────────────────────────────────────────
# Manual evaluation
# ─────────────────────────────────────────────────────────────

@router.post("/run", response_model=AlertRunSummaryOut, dependencies=[_ADMIN])
def run_now(
    tenant_id: str = Depends(get_tenant_id),
    user_identity: str = Depends(get_user_identity),
    cap_date: date | None = Query(None),
    dry_run: bool = Query(False),
):
    """Evaluate the newest capture pair now. Synchronous — it is ~30 ms of SQL.

    Returns a full summary even when it creates nothing. "Evaluated 95 groups
    against 2026-08-12 vs 2026-08-10, 8 matched, 8 already recorded" is a much
    better answer than a silent no-op, and it puts the age of the data in front
    of whoever is asking whether the feed is live.
    """
    if not is_alertable(user_identity):
        raise HTTPException(400, f"alerting is not available for {user_identity}")
    summary = runner.run_latest(
        tenant_id, user_identity, cap_date=cap_date, dry_run=dry_run,
        mode="manual" if not dry_run else "preview")
    return AlertRunSummaryOut(**{
        k: v for k, v in summary.to_dict().items() if k != "samples"})


# ─────────────────────────────────────────────────────────────
# Create / delete user rule instances
# ─────────────────────────────────────────────────────────────

# Guards the 15-minute sweep: every active instance is a full handler pass over
# the capture pair, so an unbounded list would let one tenant slow everyone's
# evaluation tick.
MAX_INSTANCES = 20


@router.post("/rules", response_model=AlertRuleOut, status_code=201,
             dependencies=[_ADMIN])
def create_rule(
    body: AlertRuleCreate,
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
    current_user: dict = Depends(get_current_user),
    user_identity: str = Depends(get_user_identity),
):
    """Create a user-owned INSTANCE of a catalogue rule type.

    The instance runs the same evaluator function as its family preset under
    its own minted rule_key, so its events, dedupe space and edge-trigger
    ledger stay fully separate from the preset's. Free-form conditions remain
    impossible: the merged condition is validated by the family's model with
    extra="forbid", so the evaluator still only ever runs conditions it
    defined itself.
    """
    import uuid as _uuid

    preset = get_preset(body.preset_key)
    if preset is None:
        raise HTTPException(422, detail={
            "message": f"unknown rule type {body.preset_key}",
            "errors": [{"field": "preset_key", "error": "unknown rule type"}],
        })

    count = db.execute(text(
        "SELECT count(*) FROM alert_rule WHERE is_preset = false AND preset_key IS NOT NULL"
    )).scalar() or 0
    if count >= MAX_INSTANCES:
        raise HTTPException(422, detail={
            "message": (f"this tenant already has {MAX_INSTANCES} custom rules; "
                        "delete one before adding another"),
        })

    name = body.name.strip()
    if not name:
        raise HTTPException(422, detail={
            "message": "invalid name",
            "errors": [{"field": "name", "error": "name cannot be blank"}],
        })

    try:
        condition = preset.validate_condition(
            {**preset.defaults(), **(body.condition or {})})
    except ValidationError as exc:
        raise HTTPException(422, detail={
            "message": "invalid condition",
            "errors": [
                {"field": ".".join(str(p) for p in e["loc"]), "error": e["msg"]}
                for e in exc.errors()
            ],
        })

    if body.is_active:
        missing = missing_requirements(preset, condition)
        if missing:
            raise HTTPException(422, detail={
                "message": (
                    f"{preset.name} needs {', '.join(missing)} before it can be "
                    f"switched on - without it the rule would match every route."
                ),
                "missing": missing,
            })

    for _ in range(3):
        rule_key = f"{body.preset_key}__{_uuid.uuid4().hex[:8]}"
        inserted = db.execute(
            text("""
                INSERT INTO alert_rule (
                    tenant_id, name, description, domain, rule_type,
                    condition_json, is_active, owner, rule_key, is_preset,
                    preset_key, severity_default, updated_by_user_id
                ) VALUES (
                    CAST(:t AS uuid), :name, :desc, :domain, :rtype,
                    CAST(:cond AS jsonb), :active, :owner, :key, false,
                    :preset, :sev, CAST(:uid AS uuid)
                )
                ON CONFLICT (tenant_id, rule_key) DO NOTHING
                RETURNING id
            """),
            {"t": tenant_id, "name": name, "desc": preset.description,
             "domain": preset.domain, "rtype": preset.rule_type,
             "cond": json.dumps(condition), "active": body.is_active,
             "owner": current_user.get("email") or "user",
             "key": rule_key, "preset": body.preset_key,
             "sev": preset.severity_default, "uid": _user_id(current_user)},
        ).first()
        if inserted is not None:
            break
    else:
        raise HTTPException(500, "could not mint a unique rule key")

    _commit(db, tenant_id)
    logger.info(
        "ALERT_RULE_CREATED actor=%s preset_key=%s rule_key=%s active=%s",
        current_user.get("email"), body.preset_key, rule_key, body.is_active,
    )
    row = db.execute(text(f"{_RULE_SELECT} WHERE r.rule_key = :k"),
                     {"k": rule_key}).first()
    options = _available_options(db, user_identity) if is_alertable(user_identity) else None
    return _rule_out(row, preset, options)


@router.delete("/rules/{rule_key}", status_code=204, dependencies=[_ADMIN])
def delete_rule(
    rule_key: str,
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
    current_user: dict = Depends(get_current_user),
):
    """Delete any rule, and with it its alert history.

    Two mechanisms behind one verb, because resurrection risk differs:

    - Instances: hard DELETE. alert_event.rule_id cascades, and their minted
      rule_keys are never reused, so a deleted edge-trigger ledger can never be
      half-resurrected under the same key. A sweep evaluating this tenant
      concurrently FK-aborts once and the next tick is idempotent.
    - Built-ins: soft delete (deleted_at tombstone) with an explicit event
      purge. The row must survive, or _ensure_presets would quietly re-seed the
      rule with defaults on the next settings visit — a delete that undoes
      itself. Restore brings it back switched off with its last-tuned settings;
      because the purge emptied its state ledger, an edge-triggered built-in
      re-announces currently-bad states after restore, which is honest if noisy.

    The built-in path has no FK backstop: a sweep that loaded the rule before
    the tombstone landed can insert events AFTER the purge (the row survives,
    so the insert succeeds where an instance's would abort). That is why the
    purge runs on EVERY delete of a built-in, tombstoned already or not —
    retrying the DELETE is the documented way to clear such orphans. Deleting
    an already-deleted built-in therefore stays a 204, purge included.
    """
    row = db.execute(
        text("SELECT id, is_preset, deleted_at, name FROM alert_rule WHERE rule_key = :k"),
        {"k": rule_key},
    ).first()
    if row is None:
        raise HTTPException(404, f"no rule {rule_key}")

    events = db.execute(
        text("SELECT count(*) FROM alert_event WHERE rule_id = :rid"),
        {"rid": str(row.id)},
    ).scalar() or 0

    if row.is_preset:
        db.execute(
            text("DELETE FROM alert_event WHERE rule_id = :rid"),
            {"rid": str(row.id)})
        if row.deleted_at is None:
            db.execute(
                text("""
                    UPDATE alert_rule
                       SET deleted_at = now(), is_active = false,
                           updated_at = now(),
                           updated_by_user_id = CAST(:uid AS uuid)
                     WHERE rule_key = :k
                """),
                {"uid": _user_id(current_user), "k": rule_key})
    else:
        db.execute(text("DELETE FROM alert_rule WHERE rule_key = :k"),
                   {"k": rule_key})

    _commit(db, tenant_id)
    logger.info(
        "ALERT_RULE_DELETED actor=%s rule_key=%s name=%r builtin=%s events_removed=%s",
        current_user.get("email"), rule_key, row.name, row.is_preset, events,
    )


@router.post("/rules/{rule_key}/restore", response_model=AlertRuleOut,
             dependencies=[_ADMIN])
def restore_rule(
    rule_key: str,
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
    current_user: dict = Depends(get_current_user),
    user_identity: str = Depends(get_user_identity),
):
    """Bring a deleted built-in rule back — switched off, last settings kept.

    Only built-ins are restorable: instances are hard-deleted and gone. Comes
    back inactive deliberately, so the admin re-tunes (or at least re-reads)
    the rule before it fires again — its event ledger was purged on delete, so
    an edge-triggered family will re-announce currently-bad states on its
    first evaluation after re-activation.
    """
    row = db.execute(
        text("SELECT id, is_preset, deleted_at FROM alert_rule WHERE rule_key = :k"),
        {"k": rule_key},
    ).first()
    if row is None:
        raise HTTPException(404, f"no rule {rule_key}")
    if not row.is_preset:
        raise HTTPException(400, "only built-in rules can be restored")

    if row.deleted_at is not None:
        db.execute(
            text("""
                UPDATE alert_rule
                   SET deleted_at = NULL, is_active = false,
                       updated_at = now(),
                       updated_by_user_id = CAST(:uid AS uuid)
                 WHERE rule_key = :k
            """),
            {"uid": _user_id(current_user), "k": rule_key})
        _commit(db, tenant_id)
        logger.info("ALERT_RULE_RESTORED actor=%s rule_key=%s",
                    current_user.get("email"), rule_key)

    row = db.execute(text(f"{_RULE_SELECT} WHERE r.rule_key = :k"),
                     {"k": rule_key}).first()
    options = _available_options(db, user_identity) if is_alertable(user_identity) else None
    return _rule_out(row, get_preset(row.preset_key), options)
