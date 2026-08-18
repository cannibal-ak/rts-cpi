#!/usr/bin/env python3
"""Superset zoom fix — dev host patcher.

Phase 1: 3871 entry chunk — legendTopRightOffset 55 -> 115 (de-crowd the
         legend/pager/selector strip away from the toolbox zoom icons).
Phase 2: 14 viz chunk files — wrap the Echart wrapper's
         `REF.current.setOption(OPT,!0)` so the current dataZoom window is
         snapshotted before the notMerge rebuild and re-applied after it,
         guarded so non-zoomable charts and error paths behave exactly as
         before.

Run from ~/CPI. Idempotent: skips files already patched.
"""
import re
import subprocess
import sys

PATCH_DIR = "superset-patches"
CONTAINER = "cpi-superset-1"
ASSETS = "/app/superset/static/assets"

CHUNKS = [
    "14c3cf97fcb6a0f990f2", "1c187a0a9fcefc88107c", "1ec85bcbb6d2cf6e10ef",
    "1fee1faa5797751fd6c9", "262c25b3f6f7f27f99a2", "2804d456171bf906397e",
    "40eaaf35ba3c1e848566", "4c1599a194b3d4787f35", "8ba96a087056d5ea2806",
    "a348224739c48b2428cd", "ad1ee9250614e7b3704f", "ba62dfe2787f02795985",
    "f619b818057afb41eb4a", "f6f6fba78b433a2dc950",
]

# Anchored on the effect tail `)}),[` so only the Echart wrapper call matches.
EFFECT_RE = re.compile(
    r"([A-Za-z_$][\w$]*)\.current\.setOption\(([A-Za-z_$][\w$]*),!0\)(\)\}\),\[)"
)

REPLACEMENT = (
    "(function(){{var _c={ref}.current,_z=null;"
    "try{{var _o=_c.getOption();_z=_o&&_o.dataZoom}}catch(_e){{}}"
    "_c.setOption({opt},!0);"
    "try{{if(_z&&_z.length){{var _s=_z[0].start||0,_n=_z[0].end==null?100:_z[0].end;"
    "if((_s>0||_n<100)&&{opt}&&{opt}.dataZoom&&{opt}.dataZoom.length)"
    '_c.dispatchAction({{type:"dataZoom",dataZoomIndex:0,start:_s,end:_n}})}}}}'
    "catch(_e){{}}}})(){tail}"
)

MARKER = "dataZoomIndex:0,start:_s,end:_n"


def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("FAIL: %s\n%s" % (cmd, r.stderr))
    return r.stdout


def main():
    # ── Phase 1: legend offset in the already-mounted 3871 chunk ──
    p3871 = f"{PATCH_DIR}/3871.c687a6d83eaaee71a216.entry.js"
    data = open(p3871, encoding="utf-8").read()
    if "legendTopRightOffset:115" in data:
        print("3871: legend offset already 115, skipping")
    else:
        n = data.count("legendTopRightOffset:55")
        if n != 1:
            sys.exit(f"3871: expected exactly 1 occurrence, found {n} — aborting")
        data = data.replace("legendTopRightOffset:55", "legendTopRightOffset:115")
        open(p3871, "w", encoding="utf-8").write(data)
        print("3871: legendTopRightOffset 55 -> 115 OK")

    # ── Phase 2: copy chunks out of the container and patch each ──
    for h in CHUNKS:
        fname = f"{h}.chunk.js"
        dest = f"{PATCH_DIR}/{fname}"
        sh(f"docker cp {CONTAINER}:{ASSETS}/{fname} {dest}")
        src = open(dest, encoding="utf-8").read()
        if MARKER in src:
            print(f"{fname}: already patched, skipping")
            continue
        matches = list(EFFECT_RE.finditer(src))
        if len(matches) != 1:
            sys.exit(f"{fname}: expected exactly 1 effect match, found {len(matches)} — aborting")
        m = matches[0]
        ref, opt, tail = m.group(1), m.group(2), m.group(3)
        patched = src[: m.start()] + REPLACEMENT.format(ref=ref, opt=opt, tail=tail) + src[m.end():]
        open(dest, "w", encoding="utf-8").write(patched)
        print(f"{fname}: patched (ref={ref}, opt={opt})")

    print("all done")


if __name__ == "__main__":
    main()
