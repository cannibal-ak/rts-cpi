"""The alerts evaluator — the only thing in the codebase that writes alert_event.

Design notes worth knowing before changing anything here:

IDEMPOTENCY comes from four independent layers, in order of how much they
matter: the unique index on (tenant_id, dedupe_key) with ON CONFLICT DO NOTHING
is the real guarantee; a per-tenant advisory lock stops two runs computing at
once; `expires` on the beat entry stops a backed-up queue stacking ticks; and
the edge-triggered state comparison is the semantic layer on top. A beat tick, a
manual run and a backfill can all race on the same capture pair and the result
is byte-identical.

EDGE TRIGGERING is why the two rule families key differently. A price move IS a
transition between two captures, so one event per scope per capture is right. A
rank change is a state that can persist: keying on the capture alone would
re-fire every single day a rank stayed bad, so those events key on the capture
AND the new state, and we only emit when the state differs from the last one
recorded for that scope.

BACKFILL HONESTY. When run in backfill mode, triggered_at is the capture date's
own business time, not the moment we computed it — a fare that moved on the 12th
moved on the 12th. `evaluation_mode` records that the row was computed
retroactively and `payload.evaluated_at` records when. The row therefore states
both truths and neither is invented. What we never do is scatter triggered_at
with jitter to look organic; that is where retroactive evaluation would stop
being evaluation and start being fabrication.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.alerts import queries as q
from app.services.alerts.presets import PRESETS, PRESET_ORDER, get_preset

logger = logging.getLogger("uvicorn.error")

# Backfilled events land at this UTC time on their own capture date. A fixed
# hour, deliberately: it is roughly when a capture lands, and a constant is
# honest where randomised jitter would be dressing.
BACKFILL_HOUR = time(6, 0, tzinfo=timezone.utc)

# A baseline capture must carry at least this fraction of the recent median row
# count. DA's 2026-08-11 has 9,612 rows against a ~16,100 median (60%) — a
# partial capture with a different flight mix, which manufactures phantom moves
# if compared against. At 0.70 it is correctly rejected and the evaluator falls
# back to 2026-08-10.
COMPLETENESS_RATIO = 0.70
COMPLETENESS_SAMPLE = 10


@dataclass
class EvalSummary:
    tenant_code: str
    cap_date: date | None = None
    prev_cap_date: date | None = None
    cap_date_age_days: int | None = None
    rules_evaluated: list[str] = field(default_factory=list)
    groups_evaluated: int = 0
    events_created: int = 0
    events_suppressed_dedupe: int = 0
    # Recorded for the state ledger but deliberately not shown to the user.
    events_suppressed_delivery: int = 0
    groups_skipped_currency: int = 0
    captures_skipped_incomplete: int = 0
    duration_ms: int = 0
    mode: str = "live"
    note: str | None = None
    # Populated only on dry runs, and capped — this is what "preview a threshold
    # before saving it" renders. Showing real matching rows is a more honest
    # test-fire than injecting a synthetic event.
    samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("cap_date", "prev_cap_date"):
            if d[k] is not None:
                d[k] = d[k].isoformat()
        return d


SAMPLE_CAP = 20


# ─────────────────────────────────────────────────────────────
# Rule loading
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LoadedRule:
    id: str
    rule_key: str
    name: str
    severity: str
    condition: dict[str, Any]


def load_active_rules(db: Session, tenant_id: str, rule_keys: list[str] | None = None) -> list[LoadedRule]:
    """Active preset rules for a tenant, in evaluation order.

    Non-preset rules are ignored on purpose: they carry free-form condition JSON
    the engine has no definition for, so running them would mean guessing.
    """
    rows = db.execute(
        text("""
            SELECT id, rule_key, name, severity_default, condition_json
              FROM alert_rule
             WHERE tenant_id = CAST(:tid AS uuid)
               AND is_active
               AND is_preset
        """),
        {"tid": tenant_id},
    ).all()

    loaded = {
        r.rule_key: LoadedRule(
            id=str(r.id), rule_key=r.rule_key, name=r.name,
            severity=r.severity_default,
            condition=r.condition_json if isinstance(r.condition_json, dict) else {},
        )
        for r in rows
        if r.rule_key in PRESETS and (rule_keys is None or r.rule_key in rule_keys)
    }
    return [loaded[k] for k in PRESET_ORDER if k in loaded]


# ─────────────────────────────────────────────────────────────
# Capture-pair selection
# ─────────────────────────────────────────────────────────────

def _complete_captures(
    db: Session, tenant_code: str, caps: list[date]
) -> tuple[list[date], list[date]]:
    """Split captures into (complete, skipped) against the median row count.

    The median is taken over the whole window rather than a trailing sample, so
    one anomalous week cannot drag the floor down far enough to admit partial
    days elsewhere in the range.
    """
    if not caps:
        return [], []
    counts = q.capture_row_counts_since(db, tenant_code, caps[0])
    present = [counts[c] for c in caps if c in counts]
    if not present:
        return caps, []
    ordered = sorted(present)
    median = ordered[len(ordered) // 2]
    floor = median * COMPLETENESS_RATIO

    keep, skip = [], []
    for c in caps:
        n = counts.get(c)
        if n is None or n >= floor:
            keep.append(c)
        else:
            skip.append(c)
            logger.info(
                "ALERT_BACKFILL_SKIP_INCOMPLETE tenant=%s cap_date=%s rows=%s floor=%.0f",
                tenant_code, c, n, floor,
            )
    return keep, skip


def is_complete(db: Session, tenant_code: str, cap_date: date) -> tuple[bool, int, float]:
    """Is this capture carrying a normal number of rows? -> (ok, rows, floor)

    The live path must check the CURRENT capture, not just the baseline. It
    previously checked only the baseline, while the backfill filtered both — so
    the two disagreed and the live one was the permissive side. That gap is
    reachable without anyone typing a flag:

      * the ingestion hook fires 5s after the FIRST file of a day commits, and a
        capture assembled from several files is definitionally partial at that
        moment;
      * the 15-minute beat tick evaluates whatever max(cap_date) is, including a
        capture still being written.

    And the damage is permanent, because dedupe_key embeds cap_date and the
    insert is ON CONFLICT DO NOTHING: the earliest, most partial reading wins and
    every later tick carrying the corrected data is swallowed as a duplicate. It
    also poisons the position rules, whose state ledger IS the event table — a
    phantom 'cheapest' row makes the next real capture emit a spurious loss.
    """
    recent = q.recent_cap_dates(
        db, tenant_code, limit=COMPLETENESS_SAMPLE + 1, before=cap_date)
    counts = q.capture_row_counts(db, tenant_code, recent[:COMPLETENESS_SAMPLE])
    own = q.capture_row_counts(db, tenant_code, [cap_date]).get(cap_date, 0)
    if not counts:
        return True, own, 0.0          # nothing to judge against
    ordered = sorted(counts.values())
    median = ordered[len(ordered) // 2]
    floor = median * COMPLETENESS_RATIO
    return own >= floor, own, floor


def choose_baseline(
    db: Session, tenant_code: str, cap_date: date, summary: EvalSummary
) -> date | None:
    """The newest complete capture strictly before `cap_date`.

    Walks back past partial captures rather than comparing against one, because
    a capture with 60% of the usual rows has a different flight mix and every
    difference reads as a price move that never happened.

    The candidate window is fetched WITH `before=cap_date` rather than taking
    the newest captures overall and filtering here. An earlier version did the
    latter, which worked for the newest capture and silently failed for every
    older one: asked to evaluate a date behind the newest ~15, the filter left
    nothing and this returned None. That is not hypothetical — the ingestion
    hook passes `job.file_date`, so re-ingesting an older file would have
    evaluated to nothing at all, quietly.
    """
    recent = q.recent_cap_dates(
        db, tenant_code, limit=COMPLETENESS_SAMPLE + 5, before=cap_date)
    if not recent:
        return None
    counts = q.capture_row_counts(db, tenant_code, recent[:COMPLETENESS_SAMPLE])
    if not counts:
        # No counts to judge against — the immediately preceding capture is a
        # better answer than refusing to evaluate at all.
        return recent[0]
    ordered = sorted(counts.values())
    median = ordered[len(ordered) // 2]
    floor = median * COMPLETENESS_RATIO

    for candidate in recent:
        n = counts.get(candidate)
        if n is None:                      # outside the sampled window; trust it
            return candidate
        if n >= floor:
            return candidate
        summary.captures_skipped_incomplete += 1
        logger.info(
            "ALERT_EVAL_SKIP_INCOMPLETE tenant=%s cap_date=%s rows=%s floor=%.0f",
            tenant_code, candidate, n, floor,
        )
    return None


# ─────────────────────────────────────────────────────────────
# Event construction
# ─────────────────────────────────────────────────────────────

def _money(value: float | None, currency: str | None) -> str:
    if value is None:
        return "n/a"
    return f"{currency or ''} {value:,.2f}".strip()


def _insert_event(
    db: Session,
    *,
    tenant_id: str,
    rule: LoadedRule,
    severity: str,
    scope_key: str,
    dedupe_key: str,
    message: str,
    payload: dict[str, Any],
    observed_at: date,
    prev_observed_at: date | None,
    mode: str,
    delivery_status: str = "delivered",
) -> bool:
    """Insert one event. Returns False when the dedupe index suppressed it."""
    triggered_at = (
        datetime.combine(observed_at, BACKFILL_HOUR)
        if mode == "backfill"
        else datetime.now(timezone.utc)
    )
    payload = dict(payload)
    payload["evaluated_at"] = datetime.now(timezone.utc).isoformat()
    payload["rule_key"] = rule.rule_key

    result = db.execute(
        text("""
            INSERT INTO alert_event (
                id, tenant_id, rule_id, rule_key, rule_name,
                scope_key, dedupe_key, triggered_at, observed_at, prev_observed_at,
                severity, message, payload, evaluation_mode, delivery_status
            ) VALUES (
                gen_random_uuid(), CAST(:tid AS uuid), CAST(:rid AS uuid), :rule_key, :rule_name,
                :scope_key, :dedupe_key, :triggered_at, :observed_at, :prev_observed_at,
                :severity, :message, CAST(:payload AS jsonb), :mode, :delivery
            )
            ON CONFLICT (tenant_id, dedupe_key) DO NOTHING
            RETURNING id
        """),
        {
            "tid": tenant_id, "rid": rule.id, "rule_key": rule.rule_key,
            "rule_name": rule.name, "scope_key": scope_key, "dedupe_key": dedupe_key,
            "triggered_at": triggered_at, "observed_at": observed_at,
            "prev_observed_at": prev_observed_at, "severity": severity,
            "message": message, "payload": json.dumps(payload), "mode": mode,
            "delivery": delivery_status,
        },
    ).first()
    return result is not None


def _emit(
    db, summary: EvalSummary, dry_run: bool, *,
    severity: str, message: str, payload: dict[str, Any],
    delivery_status: str = "delivered", **kw
) -> None:
    """Single exit point for every rule: sample it, or write it.

    A `delivery_status` other than 'delivered' still WRITES the row. That is the
    whole point: for the position rules the event table is also the state
    ledger, so an event that is merely not shown must still be recorded or the
    edge detector loses its place. Read paths filter these out.
    """
    silent = delivery_status != "delivered"
    if dry_run:
        if not silent:
            summary.events_created += 1
            if len(summary.samples) < SAMPLE_CAP:
                summary.samples.append(
                    {"severity": severity, "message": message, "payload": payload})
        else:
            summary.events_suppressed_delivery += 1
        return
    created = _insert_event(db, severity=severity, message=message,
                            payload=payload, delivery_status=delivery_status, **kw)
    if silent:
        summary.events_suppressed_delivery += created
    else:
        summary.events_created += created
    summary.events_suppressed_dedupe += (not created)


# ─────────────────────────────────────────────────────────────
# Rule family 1 — competitor price move
# ─────────────────────────────────────────────────────────────

def _eval_price_move(
    db, tenant_id, rule, cur, prev, summary, mode, dry_run
) -> None:
    cond = PRESETS["comp_price_move"].model(**rule.condition).model_dump()
    windows = set(cond["windows"])
    only_comps = set(cond["competitors"] or [])
    only_routes = set(cond["routes"] or [])

    for key in cur.competitors.keys() & prev.competitors.keys():
        route, window, comp = key
        if window not in windows:
            continue
        if only_comps and comp not in only_comps:
            continue
        if only_routes and route not in only_routes:
            continue

        c, p = cur.competitors[key], prev.competitors[key]
        summary.groups_evaluated += 1

        # Never compare across currencies. ref_curr/comp_curr are nullable with
        # a GBP server default, so uniform USD is a property of this feed, not a
        # guarantee of the schema — and silently reading 200 GBP as 200 USD
        # would be the worst bug this feature could ship.
        if c.currency != p.currency:
            summary.groups_skipped_currency += 1
            continue
        if not p.fare:
            continue

        delta_abs = c.fare - p.fare
        delta_pct = 100.0 * delta_abs / p.fare
        if abs(delta_pct) < cond["move_pct"]:
            continue
        if abs(delta_abs) < cond["min_abs_move"]:
            continue
        if cond["direction"] == "down" and delta_abs >= 0:
            continue
        if cond["direction"] == "up" and delta_abs <= 0:
            continue

        verb = "cut" if delta_abs < 0 else "raised"
        message = (
            f"{comp} {verb} its {route} fare {abs(delta_pct):.1f}% "
            f"({_money(p.fare, p.currency)} → {_money(c.fare, c.currency)}) "
            f"for departures {window.replace('-', '–')} days out."
        )
        payload = {
            "route": route, "origin": c.origin, "destination": c.destination,
            "competitor": comp, "window": window,
            "metric": "min_available_fare", "currency": c.currency,
            "prev_value": p.fare, "current_value": c.fare,
            "delta_abs": round(delta_abs, 2), "delta_pct": round(delta_pct, 2),
            "observations": c.observations, "prev_observations": p.observations,
            "direction": "down" if delta_abs < 0 else "up",
        }
        _emit(
            db, summary, dry_run,
            tenant_id=tenant_id, rule=rule, severity=rule.severity,
            scope_key=f"move|{route}|{comp}|{window}",
            dedupe_key=f"move|{route}|{comp}|{window}|{cur.cap_date}",
            message=message, payload=payload,
            observed_at=cur.cap_date, prev_observed_at=prev.cap_date, mode=mode,
        )


# ─────────────────────────────────────────────────────────────
# Rule family 2 — competitive position
# ─────────────────────────────────────────────────────────────

def _rank_for(own, competitors, route, window, min_gap_pct) -> tuple[int, int, str | None, float | None]:
    """Our rank on a route x window, plus the best competitor.

    Only competitors quoting the same currency count toward the rank.
    """
    threshold = own.fare * (1.0 - min_gap_pct / 100.0)
    cheaper = 0
    best_al, best_fare = None, None
    for (r, w, comp), cf in competitors.items():
        if r != route or w != window:
            continue
        if cf.currency != own.currency:
            continue
        if best_fare is None or cf.fare < best_fare:
            best_al, best_fare = comp, cf.fare
        if cf.fare < threshold:
            cheaper += 1
    return 1 + cheaper, cheaper, best_al, best_fare


def _eval_position(
    db, tenant_id, rule, cur, prev, summary, mode, dry_run
) -> None:
    cond = PRESETS["undercut_position"].model(**rule.condition).model_dump()
    windows = set(cond["windows"])
    only_routes = set(cond["routes"] or [])
    max_rank = cond["max_rank"]
    min_gap = cond["min_gap_pct"]

    for (route, window), own in cur.own.items():
        if window not in windows:
            continue
        if only_routes and route not in only_routes:
            continue
        if not own.fare:
            continue

        summary.groups_evaluated += 1
        rank, cheaper, best_al, best_fare = _rank_for(
            own, cur.competitors, route, window, min_gap)
        state = "cheapest" if rank <= max_rank else "undercut"
        scope_key = f"rank|{route}|{window}"

        previous = q.last_emitted_state(db, tenant_id, scope_key, cur.cap_date)
        if previous == state:
            continue
        # First time we have ever looked at this scope: only a bad state is
        # news. Announcing "we are cheapest" for every route on day one would
        # bury the two that matter.
        if previous is None and state == "cheapest":
            continue
        # NOT a `continue`. The state ledger IS alert_event, so skipping the
        # write here would leave the stored state at 'undercut' forever: the
        # next genuine undercut would then match `previous == state` above and
        # be dropped, and the scope would go permanently silent after its first
        # alert. Measured on the DA backfill: 101 undercut alerts collapse to
        # 24 � 77 real losses of the cheapest position emitting nothing at all.
        # So record it, and mark it undelivered instead.
        recovery_muted = (state == "cheapest" and not cond["notify_on_recovery"])

        if state == "undercut":
            severity = rule.severity
            message = (
                f"We are no longer cheapest on {route} for departures "
                f"{window.replace('-', '–')} days out — rank {rank} of "
                f"{own.competitor_count + 1}. "
                f"{best_al} at {_money(best_fare, own.currency)} against our "
                f"{_money(own.fare, own.currency)}."
            )
        else:
            severity = "info"
            message = (
                f"We are cheapest again on {route} for departures "
                f"{window.replace('-', '–')} days out at "
                f"{_money(own.fare, own.currency)}."
            )

        payload = {
            "route": route, "origin": own.origin, "destination": own.destination,
            "window": window, "metric": "min_available_fare",
            "currency": own.currency, "state": state,
            "da_fare": own.fare, "da_rank": rank,
            "cheaper_competitors": cheaper,
            # Six of DA's twelve routes carry exactly one competitor, so "rank 1
            # of 2" is a two-horse race. Shipping the count lets the UI say so
            # instead of implying a market analysis.
            "competitor_count": own.competitor_count,
            "best_competitor": best_al, "best_competitor_fare": best_fare,
            "min_gap_pct": min_gap, "max_rank": max_rank,
        }
        _emit(
            db, summary, dry_run,
            tenant_id=tenant_id, rule=rule, severity=severity,
            delivery_status="suppressed" if recovery_muted else "delivered",
            scope_key=scope_key,
            dedupe_key=f"rank|{route}|{window}|{cur.cap_date}|{state}",
            message=message, payload=payload,
            observed_at=cur.cap_date, prev_observed_at=prev.cap_date, mode=mode,
        )


# ─────────────────────────────────────────────────────────────
# Rule family 3 — absolute price line
# ─────────────────────────────────────────────────────────────

def _eval_price_threshold(
    db, tenant_id, rule, cur, prev, summary, mode, dry_run
) -> None:
    cond = PRESETS["comp_price_threshold"].model(**rule.condition).model_dump()
    value = cond["value"]
    only_routes = set(cond["routes"] or [])
    if value is None or not only_routes:
        # The API refuses to activate the rule in this state; belt-and-braces
        # so a hand-edited row cannot make the evaluator fire on everything.
        summary.note = "comp_price_threshold active but unconfigured; skipped"
        return

    windows = set(cond["windows"])
    only_comps = set(cond["competitors"] or [])
    op = cond["operator"]

    def _state(fare: float) -> str:
        if op == "below":
            return "below" if fare < value else "above"
        return "above" if fare > value else "below"

    for key, c in cur.competitors.items():
        route, window, comp = key
        if window not in windows or route not in only_routes:
            continue
        if only_comps and comp not in only_comps:
            continue
        p = prev.competitors.get(key)
        if p is None or c.currency != p.currency:
            continue

        summary.groups_evaluated += 1
        cur_state, prev_state = _state(c.fare), _state(p.fare)
        # The rule is "crosses", not "is" — only the crossing is news.
        if cur_state == prev_state or cur_state != op:
            continue

        message = (
            f"{comp} moved {op} {_money(value, c.currency)} on {route} "
            f"({_money(p.fare, p.currency)} → {_money(c.fare, c.currency)}) "
            f"for departures {window.replace('-', '–')} days out."
        )
        payload = {
            "route": route, "origin": c.origin, "destination": c.destination,
            "competitor": comp, "window": window, "currency": c.currency,
            "metric": "min_available_fare", "operator": op, "threshold": value,
            "prev_value": p.fare, "current_value": c.fare, "state": cur_state,
        }
        _emit(
            db, summary, dry_run,
            tenant_id=tenant_id, rule=rule, severity=rule.severity,
            scope_key=f"cross|{route}|{comp}|{window}",
            dedupe_key=f"cross|{route}|{comp}|{window}|{cur.cap_date}|{cur_state}",
            message=message, payload=payload,
            observed_at=cur.cap_date, prev_observed_at=prev.cap_date, mode=mode,
        )


_DISPATCH = {
    "comp_price_move": _eval_price_move,
    "undercut_position": _eval_position,
    "comp_price_threshold": _eval_price_threshold,
}


# ─────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────

def prepare_session(db: Session) -> None:
    """Per-transaction guards every evaluation runs under.

    Parallel workers buy nothing on aggregates this small and cost everything
    when /dev/shm runs out — which is a production incident this table has
    already had once.
    """
    db.execute(text("SET LOCAL max_parallel_workers_per_gather = 0"))
    db.execute(text("SET LOCAL statement_timeout = '30s'"))


def evaluate_pair(
    db: Session,
    tenant_id: str,
    tenant_code: str,
    cur_cap: date,
    prev_cap: date,
    *,
    mode: str = "live",
    dry_run: bool = False,
    rule_keys: list[str] | None = None,
) -> EvalSummary:
    """Evaluate one capture pair. Idempotent."""
    started = datetime.now(timezone.utc)
    summary = EvalSummary(tenant_code=tenant_code, cap_date=cur_cap,
                          prev_cap_date=prev_cap, mode=mode)

    rules = load_active_rules(db, tenant_id, rule_keys)
    summary.rules_evaluated = [r.rule_key for r in rules]
    if not rules:
        summary.note = "no active preset rules"
        return summary

    cur = q.load_capture(db, tenant_code, cur_cap)
    prev = q.load_capture(db, tenant_code, prev_cap)

    for rule in rules:
        handler = _DISPATCH.get(rule.rule_key)
        if handler is None:
            continue
        handler(db, tenant_id, rule, cur, prev, summary, mode, dry_run)

    summary.duration_ms = int(
        (datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return summary


def preview_rule(
    db: Session,
    tenant_id: str,
    tenant_code: str,
    rule_key: str,
    condition: dict[str, Any],
    *,
    rule_id: str,
    rule_name: str,
    severity: str,
) -> EvalSummary:
    """What an UNSAVED condition would fire on the newest capture pair.

    The honest form of "test fire": it shows real rows that really match, rather
    than injecting a synthetic event to prove the pipe is connected. Writes
    nothing — the caller rolls back regardless.
    """
    summary = EvalSummary(tenant_code=tenant_code, mode="preview")
    cur_cap = q.latest_cap_date(db, tenant_code)
    if cur_cap is None:
        summary.note = "no captures for tenant"
        return summary
    prev_cap = choose_baseline(db, tenant_code, cur_cap, summary)
    if prev_cap is None:
        summary.note = "no complete baseline capture"
        return summary

    summary.cap_date, summary.prev_cap_date = cur_cap, prev_cap
    handler = _DISPATCH.get(rule_key)
    if handler is None:
        summary.note = f"unknown rule {rule_key}"
        return summary

    rule = LoadedRule(id=rule_id, rule_key=rule_key, name=rule_name,
                      severity=severity, condition=condition)
    cur = q.load_capture(db, tenant_code, cur_cap)
    prev = q.load_capture(db, tenant_code, prev_cap)
    handler(db, tenant_id, rule, cur, prev, summary, "preview", True)
    summary.rules_evaluated = [rule_key]
    return summary


def evaluate_latest(
    db: Session,
    tenant_id: str,
    tenant_code: str,
    *,
    cap_date: date | None = None,
    mode: str = "live",
    dry_run: bool = False,
) -> EvalSummary:
    """Evaluate the newest capture against the newest complete one before it."""
    summary = EvalSummary(tenant_code=tenant_code, mode=mode)
    cur = cap_date or q.latest_cap_date(db, tenant_code)
    if cur is None:
        summary.note = "no captures for tenant"
        return summary

    # Refuse a partial CURRENT capture. Skipping is not a loss: a capture that
    # is partial now becomes complete once the rest of the day's files land, and
    # the next tick picks it up. Writing it now would be the loss, because the
    # dedupe key would then reject the corrected reading forever.
    ok, rows, floor = is_complete(db, tenant_code, cur)
    if not ok:
        summary.cap_date = cur
        summary.captures_skipped_incomplete += 1
        summary.note = (
            f"capture {cur} is still incomplete ({rows} rows against a floor of "
            f"{floor:.0f}); leaving it for a later run"
        )
        logger.info(
            "ALERT_EVAL_SKIP_PARTIAL_CURRENT tenant=%s cap_date=%s rows=%s floor=%.0f",
            tenant_code, cur, rows, floor,
        )
        return summary

    summary.cap_date = cur
    summary.cap_date_age_days = (date.today() - cur).days
    if summary.cap_date_age_days > 3:
        # Not an error — DA's demo feed is deliberately frozen — but the first
        # question anyone asks of an alerts page is "is this live?", and the run
        # summary should answer it without being asked.
        logger.warning(
            "ALERT_EVAL_STALE tenant=%s cap_date=%s age_days=%s",
            tenant_code, cur, summary.cap_date_age_days,
        )

    prev = choose_baseline(db, tenant_code, cur, summary)
    if prev is None:
        summary.note = f"no complete capture before {cur} to compare against"
        return summary

    result = evaluate_pair(db, tenant_id, tenant_code, cur, prev,
                           mode=mode, dry_run=dry_run)
    result.cap_date_age_days = summary.cap_date_age_days
    result.captures_skipped_incomplete = summary.captures_skipped_incomplete
    return result


def backfill(
    db: Session,
    tenant_id: str,
    tenant_code: str,
    *,
    pairs: int = 60,
    mark_read_before_pairs: int = 5,
) -> list[EvalSummary]:
    """Evaluate the last `pairs` consecutive capture pairs, oldest first.

    Runs the SAME evaluate_pair, thresholds and completeness guard as the live
    path — this is retroactive evaluation, not a separate seeding routine, which
    is the only reason the events it produces are trustworthy.

    Then writes read receipts for everything older than the newest
    `mark_read_before_pairs` captures. Several hundred unread events is a
    nonsense badge; this leaves roughly the last week unread with the full
    history browsable behind it. It is a logged parameter, not a hidden fudge.
    """
    caps = sorted(q.recent_cap_dates(db, tenant_code, limit=pairs + 1))
    if len(caps) < 2:
        return [EvalSummary(tenant_code=tenant_code, mode="backfill",
                            note="fewer than two captures")]

    # Drop partial captures BEFORE pairing, so an incomplete day is never a
    # current or a baseline. Consecutive-pairing without this quietly bypassed
    # the guard the live path applies: DA's 2026-08-11 carries 60% of the usual
    # rows, and pairing through it produced a matched pair of phantom events —
    # "TC raised ARK-ZNZ 29.6%" on the 11th and "cut it 31.5%" on the 12th, a
    # round trip that never happened. Skipping the day bridges 08-10 to 08-12
    # and reports the one real move.
    caps, skipped = _complete_captures(db, tenant_code, caps)
    if len(caps) < 2:
        return [EvalSummary(tenant_code=tenant_code, mode="backfill",
                            note="fewer than two complete captures")]

    summaries: list[EvalSummary] = []
    for prev_cap, cur_cap in zip(caps, caps[1:]):
        summaries.append(evaluate_pair(
            db, tenant_id, tenant_code, cur_cap, prev_cap, mode="backfill"))
    if summaries:
        summaries[0].captures_skipped_incomplete = len(skipped)

    if mark_read_before_pairs > 0 and len(caps) > mark_read_before_pairs:
        cutoff = caps[-mark_read_before_pairs]
        marked = mark_read_before(db, tenant_id, cutoff)
        logger.info(
            "ALERT_BACKFILL_MARKED_READ tenant=%s cutoff=%s rows=%s",
            tenant_code, cutoff, marked,
        )

    total = sum(s.events_created for s in summaries)
    logger.info(
        "ALERT_BACKFILL_DONE tenant=%s pairs=%s events=%s",
        tenant_code, len(summaries), total,
    )
    return summaries


def mark_read_before(db: Session, tenant_id: str, cutoff: date) -> int:
    """Read receipts for every user in the tenant, for events before `cutoff`."""
    result = db.execute(
        text("""
            INSERT INTO alert_event_read (id, tenant_id, event_id, user_id)
            SELECT gen_random_uuid(), e.tenant_id, e.id, u.id
              FROM alert_event e
              JOIN app_user u ON u.tenant_id = e.tenant_id
             WHERE e.tenant_id = CAST(:tid AS uuid)
               AND e.observed_at < :cutoff
            ON CONFLICT (event_id, user_id) DO NOTHING
        """),
        {"tid": tenant_id, "cutoff": cutoff},
    )
    return result.rowcount or 0
