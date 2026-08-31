"""Portfolio check: the five PROPOSED PW rule conditions run together by the
real evaluator over the last 30 capture pairs, in memory. Writes NOTHING."""
import json
import statistics
from collections import Counter

from app.services.alerts import evaluator, queries as q, runner
from app.services.alerts.evaluator import EvalSummary, LoadedRule
from app.services.alerts.presets import get_preset

TENANT_ID = "bb000000-0000-0000-0000-000000000001"
CODE = "PW"
N_PAIRS = 30

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
        CUR_EVENTS.append({"scope": kw["scope_key"], "rule": payload.get("rule_key") or kw.get("rule_key"),
                           "msg": message})
    else:
        summary.events_suppressed_delivery += 1


q.last_emitted_state = fake_last_emitted_state
evaluator._emit = fake_emit

_real_load_capture = q.load_capture
_real_load_service = q.load_service_capture
_CAP_MEMO: dict = {}
_SVC_MEMO: dict = {}
q.load_capture = lambda db, code, cap: _CAP_MEMO.setdefault(cap, _real_load_capture(db, code, cap))
q.load_service_capture = lambda db, code, cap: _SVC_MEMO.setdefault(cap, _real_load_service(db, code, cap))

W3 = ["00-07", "08-14", "15-30"]

PROPOSED = [
    ("undercut_position",    {"min_gap_pct": 2.0, "windows": W3}),
    ("comp_price_move",      {"move_pct": 20.0, "min_abs_move": 20.0, "windows": ["08-14", "15-30"]}),
    ("service_gap",          {"min_gap_days": 4, "windows": W3}),
    ("stops_disadvantage",   {"min_days": 4, "min_day_share": 60.0, "windows": W3}),
    ("comp_price_threshold", {"operator": "below", "value": 190.0, "windows": ["00-07"],
                              "routes": ["DAR-NBO", "JRO-NBO", "ZNZ-NBO"]}),
]


def main():
    with runner.tenant_session(TENANT_ID) as db:
        caps_desc = q.recent_cap_dates(db, CODE, limit=N_PAIRS + 12)
        counts = q.capture_row_counts(db, CODE, caps_desc)
        med = statistics.median(list(counts.values())[:10] or [0])
        good = sorted(c for c in caps_desc if counts.get(c, 0) >= 0.70 * med)
        good = good[-(N_PAIRS + 1):]
        pairs = list(zip(good[:-1], good[1:]))

        rules = []
        for rule_key, overrides in PROPOSED:
            preset = get_preset(rule_key)
            condition = preset.validate_condition({**preset.defaults(), **overrides})
            rules.append(LoadedRule(id="00000000-0000-0000-0000-000000000000",
                                    rule_key=rule_key, name=preset.name,
                                    severity=preset.severity_default,
                                    condition=condition))

        per_pair = []
        by_rule = Counter()
        sample_msgs = []
        rule_keys = [r.rule_key for r in rules]
        for i, (prev_cap, cur_cap) in enumerate(pairs):
            CUR_EVENTS.clear()
            cur, prev = evaluator._load_pair(db, CODE, cur_cap, prev_cap, rule_keys)
            day_total = 0
            for rule in rules:
                summary = EvalSummary(tenant_code=CODE, cap_date=cur_cap,
                                      prev_cap_date=prev_cap, mode="preview")
                n0 = len(CUR_EVENTS)
                evaluator._DISPATCH[rule.rule_key](
                    db, TENANT_ID, rule, cur, prev, summary, "preview", True)
                got = len(CUR_EVENTS) - n0
                day_total += got
                if i > 0:
                    by_rule[rule.rule_key] += got
            per_pair.append((str(cur_cap), day_total))
            if i >= len(pairs) - 6:
                for e in CUR_EVENTS:
                    sample_msgs.append(f"{cur_cap} [{e['scope']}] {e['msg']}")

        steady = [n for _, n in per_pair[1:]]
        print(json.dumps({
            "first_fire_pair": per_pair[0],
            "steady_avg_per_day": round(sum(steady) / len(steady), 2),
            "steady_max": max(steady),
            "zero_days": sum(1 for n in steady if n == 0),
            "by_rule_steady": dict(by_rule),
            "last_pairs": per_pair[-8:],
            "sample_recent_messages": sample_msgs[-25:],
        }, indent=1, default=str))


if __name__ == "__main__":
    main()
