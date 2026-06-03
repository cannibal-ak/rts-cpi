"""Strip the hardcoded '$' from FJL dashboard-2 chart number formats, optionally
normalize two SMART_NUMBER axes for consistency, and remove the now-redundant
native Currency filter (NATIVE_FILTER-fjl-curr) from dashboard 2.

FJL fares are NOK/DKK/EUR (never USD); the '$' D3 prefix was always wrong, and a
static prefix can't track the dynamic app currency selector anyway — the React
shell now carries a "Values in <CUR>" indicator instead, so the charts show
symbol-less numbers.

Pure HTTP, mirroring 20260529_nullif_zero_fare_jy_pw.py: session+CSRF login,
GET chart/dashboard, patch params + query_context.form_data / json_metadata,
PUT back. No Superset ORM / Flask bootstrap.

Idempotent + targeted: each edit names an exact (path, expected_old, new). A field
is rewritten ONLY when its current value == expected_old. Values already == new are
skipped (re-runnable); anything else is left untouched and logged as UNEXPECTED.
Never a blind string replace.

    python 20260603_fjl_currency_symbol_and_filter.py            # dry-run
    python 20260603_fjl_currency_symbol_and_filter.py --apply    # issue PUTs
  flags:
    --no-consistency      keep slice 68/69 as SMART_NUMBER (skip ,.0f normalize)
    --no-filter-removal   keep the native Currency filter on dashboard 2
"""
import argparse
import json

import requests

SUPERSET_BASE = "http://localhost:8088"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
REFERER = "http://192.168.101.10:8088/"

DASHBOARD_ID = 2
NATIVE_FILTER_ID = "NATIVE_FILTER-fjl-curr"

# REQUIRED — strip '$' from the exact format keys (NOT a blind replace).
# {slice_id: [(dotted_path_into_params, expected_old, new), ...]}
REQUIRED_EDITS = {
    60: [("y_axis_format", "$,.0f", ",.0f")],
    62: [("valueFormat", "$,.0f", ",.0f")],
    63: [("y_axis_format", "$,.0f", ",.0f")],
    64: [
        ("column_config.cheapest_fare.d3NumberFormat", "$,.2f", ",.2f"),
        ("column_config.next_cheapest_fare.d3NumberFormat", "$,.2f", ",.2f"),
        ("column_config.price_gap.d3NumberFormat", "+$,.2f", "+,.2f"),
    ],
    66: [("y_axis_format", "$,.0f", ",.0f")],
    67: [("y_axis_format", "$,.0f", ",.0f")],
}

# OPTIONAL consistency (default ON; --no-consistency to skip).
CONSISTENCY_EDITS = {
    68: [("y_axis_format", "SMART_NUMBER", ",.0f")],
    69: [("y_axis_format", "SMART_NUMBER", ",.0f")],
}


def resolve(container, dotted):
    """Return (parent_dict, key) for a dotted path, or None if any segment is missing."""
    if not isinstance(container, dict):
        return None
    parts = dotted.split(".")
    cur = container
    for seg in parts[:-1]:
        if not isinstance(cur, dict) or seg not in cur:
            return None
        cur = cur[seg]
    if not isinstance(cur, dict) or parts[-1] not in cur:
        return None
    return cur, parts[-1]


def apply_edit(blob, dotted, old, new):
    """Returns one of: 'changed' | 'already' | 'absent' | 'unexpected', and the
    current value seen. Only mutates when current == old."""
    res = resolve(blob, dotted)
    if res is None:
        return "absent", None
    parent, key = res
    cur = parent[key]
    if cur == old:
        parent[key] = new
        return "changed", cur
    if cur == new:
        return "already", cur
    return "unexpected", cur


def make_session():
    import re
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


def process_slice(sess, sid, edits, apply):
    r = sess.get(f"{SUPERSET_BASE}/api/v1/chart/{sid}")
    if r.status_code != 200:
        return {"id": sid, "error": f"GET {r.status_code}: {r.text[:200]}"}
    slc = r.json()["result"]
    name = slc.get("slice_name")

    p = json.loads(slc.get("params") or "{}")
    qc_raw = slc.get("query_context") or ""
    q = json.loads(qc_raw) if qc_raw.strip() else {}
    fd = q.get("form_data") if isinstance(q, dict) else None

    rows = []
    nchg = 0
    for dotted, old, new in edits:
        st_p, cur_p = apply_edit(p, dotted, old, new)
        st_q, cur_q = ("absent", None)
        if isinstance(fd, dict):
            st_q, cur_q = apply_edit(fd, dotted, old, new)
        if st_p == "changed" or st_q == "changed":
            nchg += 1
        rows.append({
            "path": dotted, "old": old, "new": new,
            "params": st_p, "qc": st_q,
            "current": cur_p if cur_p is not None else cur_q,
        })

    result = {"id": sid, "slice_name": name, "rows": rows, "nchg": nchg, "applied": False}

    if apply and nchg:
        body = {"params": json.dumps(p)}
        if q:
            body["query_context"] = json.dumps(q)
        put = sess.put(f"{SUPERSET_BASE}/api/v1/chart/{sid}", json=body)
        result["put_status"] = put.status_code
        result["put_text"] = put.text[:300]
        result["applied"] = (put.status_code == 200)
    return result


def process_filter(sess, apply):
    r = sess.get(f"{SUPERSET_BASE}/api/v1/dashboard/{DASHBOARD_ID}")
    if r.status_code != 200:
        return {"error": f"GET dashboard {r.status_code}: {r.text[:200]}"}
    d = r.json()["result"]
    jm = json.loads(d.get("json_metadata") or "{}")
    nfc = jm.get("native_filter_configuration", []) or []
    present = [f for f in nfc if f.get("id") == NATIVE_FILTER_ID]
    remaining = [f.get("name") for f in nfc if f.get("id") != NATIVE_FILTER_ID]
    res = {"present": bool(present), "remaining": remaining, "applied": False}
    if not present:
        return res
    if apply:
        jm["native_filter_configuration"] = [f for f in nfc if f.get("id") != NATIVE_FILTER_ID]
        put = sess.put(
            f"{SUPERSET_BASE}/api/v1/dashboard/{DASHBOARD_ID}",
            json={"json_metadata": json.dumps(jm)},
        )
        res["put_status"] = put.status_code
        res["put_text"] = put.text[:300]
        res["applied"] = (put.status_code == 200)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Issue PUTs (else dry-run)")
    ap.add_argument("--no-consistency", action="store_true", help="Skip slice 68/69 SMART_NUMBER->,.0f")
    ap.add_argument("--no-filter-removal", action="store_true", help="Keep the native Currency filter")
    args = ap.parse_args()

    edits = dict(REQUIRED_EDITS)
    if not args.no_consistency:
        edits.update(CONSISTENCY_EDITS)

    sess = make_session()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print("=" * 80)
    print(f"FJL currency-symbol + filter migration — {mode}")
    print("=" * 80)

    results = [process_slice(sess, sid, edits[sid], args.apply) for sid in sorted(edits)]
    for r in results:
        if "error" in r:
            print(f"slice {r['id']}: ERROR {r['error']}")
            continue
        name = (r["slice_name"] or "")[:40]
        tag = ""
        if args.apply:
            tag = " [APPLIED]" if r["applied"] else (f" [PUT FAILED {r.get('put_status')}]" if r["nchg"] else " [no change]")
        print(f"\nslice {r['id']:>3}  {name}{tag}")
        for row in r["rows"]:
            if row["params"] == "changed" or row["qc"] == "changed":
                verb = "WILL CHANGE" if not args.apply else "CHANGED"
                print(f"    {verb}  {row['path']}:  {row['old']!r} -> {row['new']!r}   (params={row['params']}, qc={row['qc']})")
            elif row["params"] == "already" or (row["params"] == "absent" and row["qc"] == "already"):
                print(f"    skip      {row['path']}:  already {row['new']!r}")
            elif row["params"] == "absent" and row["qc"] == "absent":
                print(f"    skip      {row['path']}:  field absent")
            else:
                print(f"    SKIP!!    {row['path']}:  UNEXPECTED current={row['current']!r} (expected {row['old']!r}) — left untouched")
        if args.apply and r["nchg"] and not r["applied"]:
            print(f"    PUT_FAIL_BODY: {r.get('put_text')}")

    print("\n" + "-" * 80)
    if args.no_filter_removal:
        print("Phase 3 (native Currency filter removal): SKIPPED via --no-filter-removal")
    else:
        fr = process_filter(sess, args.apply)
        if "error" in fr:
            print(f"filter removal: ERROR {fr['error']}")
        elif not fr["present"]:
            print(f"filter {NATIVE_FILTER_ID}: already absent — nothing to do")
            print(f"    remaining filters: {fr['remaining']}")
        else:
            verb = "WILL REMOVE" if not args.apply else ("REMOVED" if fr["applied"] else f"REMOVE FAILED ({fr.get('put_status')})")
            print(f"filter {NATIVE_FILTER_ID}: {verb}")
            print(f"    remaining filters after removal: {fr['remaining']}")
            if args.apply and not fr["applied"]:
                print(f"    PUT_FAIL_BODY: {fr.get('put_text')}")
    print("=" * 80)


if __name__ == "__main__":
    main()
