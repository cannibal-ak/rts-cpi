"""Apply NULLIF(fare, 0) wrapper to AVG/MIN ad-hoc metrics on JY-dashboard slices.

Pure HTTP — reads slices via GET /api/v1/chart/{id}, patches params +
query_context, optionally PUTs back via the session+CSRF write flow.
No Superset ORM imports, so no Flask/SQLAlchemy bootstrap.

    python patch_slices.py          # dry-run; prints diffs, writes /tmp/patches.json
    python patch_slices.py --apply  # also issues authenticated PUTs
"""
import argparse
import json
import re

import requests

SUPERSET_BASE = "http://localhost:8088"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
REFERER = "http://192.168.101.10:8088/"

SLICE_IDS = [43, 46, 49, 50, 51, 52, 55]

# Substitutions on sqlExpression strings. MAX and COUNT are deliberately NOT
# matched. The `fare` column is the unioned ref+comp column from dataset 13.
SUBS = [
    (re.compile(r"\bAVG\(\s*fare\s*\)"), "COALESCE(AVG(COALESCE(fare, 0)), 0)"),
    (re.compile(r"\bMIN\(\s*fare\s*\)"), "COALESCE(MIN(COALESCE(fare, 0)), 0)"),
]

SAFE_GUARDS_FORBID = [
    re.compile(r"\bMAX\(\s*NULLIF"),     # never wrap MAX
    re.compile(r"\bCOUNT\(\s*NULLIF"),   # never wrap COUNT
]


def patch_expr(expr):
    if not isinstance(expr, str):
        return expr, 0
    new, total = expr, 0
    for pat, repl in SUBS:
        new, n = pat.subn(repl, new)
        total += n
    return new, total


def walk_and_patch(obj):
    """Recurse into params/query_context, patch every metric dict's sqlExpression."""
    n = 0
    if isinstance(obj, dict):
        if "expressionType" in obj and "sqlExpression" in obj:
            new_expr, c = patch_expr(obj["sqlExpression"])
            if c:
                obj["sqlExpression"] = new_expr
                n += c
        for v in obj.values():
            n += walk_and_patch(v)
    elif isinstance(obj, list):
        for v in obj:
            n += walk_and_patch(v)
    return n


def safety_check(blob):
    s = json.dumps(blob)
    for pat in SAFE_GUARDS_FORBID:
        if pat.search(s):
            raise SystemExit(f"REFUSING: forbidden pattern {pat.pattern} found")


def metric_exprs(blob):
    out = []
    def go(o):
        if isinstance(o, dict):
            if "sqlExpression" in o:
                out.append((o.get("label") or "?", o["sqlExpression"]))
            for v in o.values(): go(v)
        elif isinstance(o, list):
            for v in o: go(v)
    go(blob)
    return out


def make_session():
    s = requests.Session()
    login_page = s.get(f"{SUPERSET_BASE}/login/")
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_page.text)
    login_csrf = m.group(1) if m else ""
    s.post(
        f"{SUPERSET_BASE}/login/",
        data={"username": ADMIN_USER, "password": ADMIN_PASS, "csrf_token": login_csrf},
        allow_redirects=False,
    )
    r = s.get(f"{SUPERSET_BASE}/api/v1/security/csrf_token/")
    api_csrf = r.json()["result"]
    s.headers.update({"X-CSRFToken": api_csrf, "Referer": REFERER})
    return s


def patch_slice(sess, sid, apply):
    r = sess.get(f"{SUPERSET_BASE}/api/v1/chart/{sid}")
    if r.status_code != 200:
        return {"id": sid, "error": f"GET {r.status_code}: {r.text[:200]}"}
    slc = r.json()["result"]
    slice_name = slc.get("slice_name")

    before_params = slc.get("params") or "{}"
    before_qc = slc.get("query_context") or ""
    p = json.loads(before_params)
    q = json.loads(before_qc) if before_qc.strip() else {}

    n_p = walk_and_patch(p)
    n_q = walk_and_patch(q)

    safety_check(p)
    safety_check(q)

    new_params = json.dumps(p)
    new_qc = json.dumps(q) if q else None

    before_exprs = metric_exprs(json.loads(before_params))
    after_exprs = metric_exprs(p)

    result = {
        "id": sid,
        "slice_name": slice_name,
        "n_subs_params": n_p,
        "n_subs_query_context": n_q,
        "before_exprs": before_exprs,
        "after_exprs": after_exprs,
        "applied": False,
    }

    if apply and (n_p or n_q):
        body = {"params": new_params}
        if new_qc is not None:
            body["query_context"] = new_qc
        put = sess.put(f"{SUPERSET_BASE}/api/v1/chart/{sid}", json=body)
        result["put_status"] = put.status_code
        result["put_text"] = put.text[:300]
        result["applied"] = (put.status_code == 200)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Issue PUTs (else dry-run)")
    args = ap.parse_args()

    sess = make_session()
    results = [patch_slice(sess, sid, args.apply) for sid in SLICE_IDS]

    with open("/tmp/patches.json", "w") as f:
        json.dump(results, f, indent=2)

    print("=" * 78)
    for r in results:
        if "error" in r:
            print(f"slice {r['id']}: ERROR {r['error']}")
            continue
        if r["n_subs_params"] == 0 and r["n_subs_query_context"] == 0:
            flag = "no change"
        elif r["applied"]:
            flag = "APPLIED"
        elif args.apply:
            flag = f"FAILED ({r.get('put_status')})"
        else:
            flag = "changed (dry-run)"
        name = (r["slice_name"] or "")[:34]
        print(f"slice {r['id']:>3} {name:34s} params_subs={r['n_subs_params']} qc_subs={r['n_subs_query_context']} {flag}")
        before_map = dict(r["before_exprs"])
        after_map = dict(r["after_exprs"])
        for lbl in after_map:
            if "NULLIF" in after_map[lbl] and before_map.get(lbl) != after_map[lbl]:
                print(f"           [{lbl}]")
                print(f"             before: {before_map.get(lbl, '?')}")
                print(f"             after:  {after_map[lbl]}")
        if not r["applied"] and "put_text" in r and r.get("put_status") != 200:
            print(f"           PUT_FAIL_BODY: {r['put_text']}")
    print("=" * 78)
    print("detailed patch report: /tmp/patches.json")


if __name__ == "__main__":
    main()
