"""DA alert-tuning simulator — runs the REAL evaluator handlers over the last
N capture pairs with the state ledger and event sink replaced by in-memory
dicts. Reads the snapshot table only; writes NOTHING.

Usage: docker exec -e PYTHONPATH=/app cpi-api-1 python /tmp/da_tuning_sim.py
"""
import json
import statistics
from collections import Counter, defaultdict

from app.services.alerts import evaluator, queries as q, runner
from app.services.alerts.evaluator import EvalSummary, LoadedRule
from app.services.alerts.presets import get_preset

TENANT_ID = "ab000000-0000-0000-0000-000000000001"
CODE = "DA"
N_PAIRS = 30

# ── in-memory ledger + sink ──────────────────────────────────
STATE: dict = {}
CUR_EVENTS: list = []


def fake_last_emitted_state(db, tenant_id, scope_key, before):
    return STATE.get(scope_key)


def fake_emit(db, summary, dry_run, *, severity, message, payload,
              delivery_status="delivered", **kw):
    st = payload.get("state")
    if st is not None:
        STATE[kw["scope_key"]] = st
    if delivery_status == "delivered":
        summary.events_created += 1
        CUR_EVENTS.append({
            "scope": kw["scope_key"],
            "state": st,
            "window": payload.get("window"),
            "route": payload.get("route"),
            "competitor": payload.get("competitor"),
            "direction": payload.get("direction"),
            "delta_pct": payload.get("delta_pct"),
            "delta_abs": payload.get("delta_abs"),
        })
    else:
        summary.events_suppressed_delivery += 1


# patch the module attributes the handlers actually resolve at call time
q.last_emitted_state = fake_last_emitted_state
evaluator._emit = fake_emit

# memoise the aggregates so 30 captures load once across all scenarios
_real_load_capture = q.load_capture
_real_load_service = q.load_service_capture
_CAP_MEMO: dict = {}
_SVC_MEMO: dict = {}


def memo_load_capture(db, code, cap):
    if cap not in _CAP_MEMO:
        _CAP_MEMO[cap] = _real_load_capture(db, code, cap)
    return _CAP_MEMO[cap]


def memo_load_service(db, code, cap):
    if cap not in _SVC_MEMO:
        _SVC_MEMO[cap] = _real_load_service(db, code, cap)
    return _SVC_MEMO[cap]


q.load_capture = memo_load_capture
q.load_service_capture = memo_load_service

W3 = ["00-07", "08-14", "15-30"]

SCENARIOS = [
    # ── comp_price_move (stateless per pair) ──
    ("move A1 cur 10%/$5 w3",   "comp_price_move", {"move_pct": 10.0, "min_abs_move": 5.0,  "windows": W3}),
    ("move A2 15%/$10 w3",      "comp_price_move", {"move_pct": 15.0, "min_abs_move": 10.0, "windows": W3}),
    ("move A3 20%/$15 w3",      "comp_price_move", {"move_pct": 20.0, "min_abs_move": 15.0, "windows": W3}),
    ("move A4 20%/$20 w3",      "comp_price_move", {"move_pct": 20.0, "min_abs_move": 20.0, "windows": W3}),
    ("move A5 20%/$20 w1",      "comp_price_move", {"move_pct": 20.0, "min_abs_move": 20.0, "windows": ["00-07"]}),
    ("move A6 25%/$25 w3",      "comp_price_move", {"move_pct": 25.0, "min_abs_move": 25.0, "windows": W3}),
    ("move A7 20%/$20 w2",      "comp_price_move", {"move_pct": 20.0, "min_abs_move": 20.0, "windows": ["00-07", "08-14"]}),
    ("move A8 30%/$30 w3",      "comp_price_move", {"move_pct": 30.0, "min_abs_move": 30.0, "windows": W3}),
    # ── undercut_position (edge-triggered) ──
    ("uc U1 cur gap1 w3",       "undercut_position", {"min_gap_pct": 1.0, "windows": W3}),
    ("uc U2 gap2 w3",           "undercut_position", {"min_gap_pct": 2.0, "windows": W3}),
    ("uc U3 gap3 w3",           "undercut_position", {"min_gap_pct": 3.0, "windows": W3}),
    ("uc U4 gap5 w3",           "undercut_position", {"min_gap_pct": 5.0, "windows": W3}),
    ("uc U5 gap2 w2",           "undercut_position", {"min_gap_pct": 2.0, "windows": ["00-07", "08-14"]}),
    ("uc U6 gap5 w2",           "undercut_position", {"min_gap_pct": 5.0, "windows": ["00-07", "08-14"]}),
    ("uc U7 gap10 w3",          "undercut_position", {"min_gap_pct": 10.0, "windows": W3}),
    # ── service_gap (edge-triggered) ──
    ("sg S1 cur g3/obs4 w1",    "service_gap", {"min_gap_days": 3, "windows": ["00-07"]}),
    ("sg S2 g4 w1",             "service_gap", {"min_gap_days": 4, "windows": ["00-07"]}),
    ("sg S3 g4 w3",             "service_gap", {"min_gap_days": 4, "windows": W3}),
    ("sg S4 g5 w3",             "service_gap", {"min_gap_days": 5, "windows": W3}),
    ("sg S5 g3 w3",             "service_gap", {"min_gap_days": 3, "windows": W3}),
    # ── stops_disadvantage (edge-triggered) ──
    ("st D1 cur d3/50 w2(8-30)", "stops_disadvantage", {"min_days": 3, "min_day_share": 50.0, "windows": ["08-14", "15-30"]}),
    ("st D2 d4/60 w3",           "stops_disadvantage", {"min_days": 4, "min_day_share": 60.0, "windows": W3}),
    ("st D3 d4/60 w2(8-30)",     "stops_disadvantage", {"min_days": 4, "min_day_share": 60.0, "windows": ["08-14", "15-30"]}),
    ("st D4 d3/50 w3",           "stops_disadvantage", {"min_days": 3, "min_day_share": 50.0, "windows": W3}),
]


def main():
    out = []
    with runner.tenant_session(TENANT_ID) as db:
        # completeness-filtered capture list, mirroring the engine's guard
        caps_desc = q.recent_cap_dates(db, CODE, limit=N_PAIRS + 12)
        counts = q.capture_row_counts(db, CODE, caps_desc)
        med = statistics.median(list(counts.values())[:10] or [0])
        floor = 0.70 * med
        good = sorted(c for c in caps_desc if counts.get(c, 0) >= floor)
        good = good[-(N_PAIRS + 1):]
        pairs = list(zip(good[:-1], good[1:]))
        dropped = sorted(set(caps_desc) - set(good))

        header = {"pairs": len(pairs), "first": str(good[0]), "last": str(good[-1]),
                  "median_rows": med,
                  "dropped_incomplete": [str(d) for d in dropped if d >= good[0]]}

        for label, rule_key, overrides in SCENARIOS:
            preset = get_preset(rule_key)
            condition = preset.validate_condition({**preset.defaults(), **overrides})
            rule = LoadedRule(id="00000000-0000-0000-0000-000000000000",
                              rule_key=rule_key, name=preset.name,
                              severity=preset.severity_default, condition=condition)
            handler = evaluator._DISPATCH[rule_key]

            STATE.clear()
            per_pair = []
            all_events = []
            for prev_cap, cur_cap in pairs:
                CUR_EVENTS.clear()
                cur, prev = evaluator._load_pair(db, CODE, cur_cap, prev_cap, [rule_key])
                summary = EvalSummary(tenant_code=CODE, cap_date=cur_cap,
                                      prev_cap_date=prev_cap, mode="preview")
                handler(db, TENANT_ID, rule, cur, prev, summary, "preview", True)
                per_pair.append(summary.events_created)
                for e in CUR_EVENTS:
                    e["cap"] = str(cur_cap)
                all_events.extend(CUR_EVENTS)

            first_fire = per_pair[0]
            steady = per_pair[1:]
            scope_counts = Counter(e["scope"] for e in all_events)
            win_counts = Counter(e["window"] for e in all_events if e.get("window"))
            comp_counts = Counter(e["competitor"] for e in all_events if e.get("competitor"))
            bad_now = sorted(s for s, v in STATE.items()
                             if v in ("undercut", "gap", "behind", "below", "above"))
            out.append({
                "scenario": label,
                "first_fire": first_fire,
                "steady_total": sum(steady),
                "steady_avg_per_capture": round(sum(steady) / max(len(steady), 1), 2),
                "steady_max": max(steady) if steady else 0,
                "zero_days": sum(1 for v in steady if v == 0),
                "by_window": dict(win_counts),
                "by_competitor": dict(comp_counts.most_common(6)),
                "flappiest_scopes": scope_counts.most_common(6),
                "bad_state_now_n": len(bad_now),
                "bad_state_now": bad_now[:14],
            })

    print(json.dumps({"header": header, "results": out}, indent=1, default=str))


if __name__ == "__main__":
    main()
