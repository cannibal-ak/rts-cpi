#!/usr/bin/env python3
"""Move velocity charts from Dashboard #4 to Dashboard #1, then delete Dashboard #4."""

import sqlite3
import json

DB_PATH = "/data/superset.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ── Step 1: Get charts currently on Dashboard #4 ──
cur.execute("SELECT slice_id FROM dashboard_slices WHERE dashboard_id = 4")
velocity_chart_ids = [r[0] for r in cur.fetchall()]
print(f"Velocity charts to move: {velocity_chart_ids}")

# ── Step 2: Link velocity charts to Dashboard #1 ──
for cid in velocity_chart_ids:
    cur.execute("SELECT 1 FROM dashboard_slices WHERE dashboard_id = 1 AND slice_id = ?", (cid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (1, ?)", (cid,))
        print(f"  Linked chart {cid} to Dashboard #1")
    else:
        print(f"  Chart {cid} already on Dashboard #1")

# ── Step 3: Update Dashboard #1 position_json to include new charts ──
cur.execute("SELECT position_json FROM dashboards WHERE id = 1")
row = cur.fetchone()
positions = json.loads(row[0]) if row and row[0] else {}

# Get chart names for the velocity charts
cur.execute("SELECT id, slice_name FROM slices WHERE id IN ({})".format(",".join(str(c) for c in velocity_chart_ids)))
chart_names = {r[0]: r[1] for r in cur.fetchall()}

# Find existing ROW keys to determine the next row number
existing_rows = [k for k in positions.keys() if k.startswith("ROW-")]
max_row_num = max([int(k.split("-")[1]) for k in existing_rows], default=0)

# Add a header row for velocity section
header_key = f"HEADER-velocity"
new_row_header = f"ROW-{max_row_num + 1}"
positions[header_key] = {
    "type": "HEADER",
    "id": header_key,
    "children": [],
    "parents": ["ROOT_ID", "GRID_ID", new_row_header],
    "meta": {"text": "Velocity & Load Factor Analysis"}
}
positions[new_row_header] = {
    "type": "ROW",
    "id": new_row_header,
    "children": [header_key],
    "parents": ["ROOT_ID", "GRID_ID"],
    "meta": {"background": "BACKGROUND_TRANSPARENT"}
}

# Add velocity charts in 2 rows of 2
chart_keys = []
for i, cid in enumerate(velocity_chart_ids):
    key = f"CHART-vel-{i+1}"
    chart_keys.append(key)

row_num = max_row_num + 2
for i in range(0, len(chart_keys), 2):
    row_key = f"ROW-{row_num}"
    row_children = chart_keys[i:i+2]
    positions[row_key] = {
        "type": "ROW",
        "id": row_key,
        "children": row_children,
        "parents": ["ROOT_ID", "GRID_ID"],
        "meta": {"background": "BACKGROUND_TRANSPARENT"}
    }
    for ck in row_children:
        idx = chart_keys.index(ck)
        cid = velocity_chart_ids[idx]
        positions[ck] = {
            "type": "CHART",
            "id": ck,
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_key],
            "meta": {
                "width": 6,
                "height": 50,
                "chartId": cid,
                "sliceName": chart_names.get(cid, f"Chart {cid}")
            }
        }
    row_num += 1

# Update GRID_ID children to include new rows
grid = positions.get("GRID_ID", {})
if "children" in grid:
    grid["children"].append(new_row_header)
    for i in range(0, len(chart_keys), 2):
        grid["children"].append(f"ROW-{max_row_num + 2 + i // 2}")

cur.execute("UPDATE dashboards SET position_json = ? WHERE id = 1", (json.dumps(positions),))
print("Updated Dashboard #1 layout with velocity charts")

# ── Step 4: Remove chart links from Dashboard #4 ──
cur.execute("DELETE FROM dashboard_slices WHERE dashboard_id = 4")
print("Removed chart links from Dashboard #4")

# ── Step 5: Delete Dashboard #4 ──
cur.execute("DELETE FROM dashboards WHERE id = 4")
print("Deleted Dashboard #4")

# ── Step 5b: Delete embedded dashboard entry for #4 if any ──
cur.execute("DELETE FROM embedded_dashboards WHERE dashboard_id = 4")

# ── Verify final state ──
print()
print("=== FINAL STATE: Dashboard #1 ===")
cur.execute("SELECT s.id, s.slice_name FROM dashboard_slices ds JOIN slices s ON s.id=ds.slice_id WHERE ds.dashboard_id=1 ORDER BY s.id")
for r in cur.fetchall():
    print(f"  Chart {r[0]}: {r[1]}")

print()
print("=== ALL DASHBOARDS ===")
cur.execute("SELECT id, dashboard_title FROM dashboards ORDER BY id")
for r in cur.fetchall():
    print(f"  ID={r[0]}: {r[1]}")

conn.commit()
conn.close()
print("\nDone.")
