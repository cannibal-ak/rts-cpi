#!/usr/bin/env python3
"""Fix Dashboard #1 layout to include velocity charts properly."""

import sqlite3
import json
import random
import string

DB_PATH = "/data/superset.db"

def rand_id(prefix=""):
    """Generate a random ID like Superset uses."""
    chars = string.ascii_letters + string.digits
    return prefix + "".join(random.choices(chars, k=11))

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Read current position_json
cur.execute("SELECT position_json FROM dashboards WHERE id = 1")
row = cur.fetchone()
positions = json.loads(row[0]) if row and row[0] else {}

print(f"Existing position keys: {len(positions)}")

# Get velocity chart names
cur.execute("SELECT id, slice_name FROM slices WHERE id IN (18, 19, 20, 21)")
chart_names = {r[0]: r[1] for r in cur.fetchall()}
print(f"Velocity charts: {chart_names}")

# Remove any half-applied keys from previous attempt
keys_to_remove = [k for k in positions if "vel" in k.lower() or k == "HEADER-velocity"]
for k in keys_to_remove:
    del positions[k]
    print(f"  Removed stale key: {k}")

# Find the GRID_ID
grid = positions.get("GRID_ID", {})
grid_children = grid.get("children", [])

# Create a header row for velocity section
header_row_id = rand_id("ROW-")
header_id = rand_id("HEADER-")

positions[header_id] = {
    "type": "HEADER",
    "id": header_id,
    "children": [],
    "parents": ["ROOT_ID", "GRID_ID", header_row_id],
    "meta": {"text": "Velocity & Load Factor Analysis"}
}
positions[header_row_id] = {
    "type": "ROW",
    "id": header_row_id,
    "children": [header_id],
    "parents": ["ROOT_ID", "GRID_ID"],
    "meta": {"background": "BACKGROUND_TRANSPARENT"}
}
grid_children.append(header_row_id)

# Row 1: Charts 18, 19 (bar charts)
row1_id = rand_id("ROW-")
chart1_id = rand_id("CHART-")
chart2_id = rand_id("CHART-")

positions[chart1_id] = {
    "type": "CHART", "id": chart1_id, "children": [],
    "parents": ["ROOT_ID", "GRID_ID", row1_id],
    "meta": {"width": 6, "height": 50, "chartId": 18, "sliceName": chart_names.get(18, "Avg Seat Factor by Route")}
}
positions[chart2_id] = {
    "type": "CHART", "id": chart2_id, "children": [],
    "parents": ["ROOT_ID", "GRID_ID", row1_id],
    "meta": {"width": 6, "height": 50, "chartId": 19, "sliceName": chart_names.get(19, "Booking vs Capacity by Equipment")}
}
positions[row1_id] = {
    "type": "ROW", "id": row1_id,
    "children": [chart1_id, chart2_id],
    "parents": ["ROOT_ID", "GRID_ID"],
    "meta": {"background": "BACKGROUND_TRANSPARENT"}
}
grid_children.append(row1_id)

# Row 2: Charts 20, 21 (tables)
row2_id = rand_id("ROW-")
chart3_id = rand_id("CHART-")
chart4_id = rand_id("CHART-")

positions[chart3_id] = {
    "type": "CHART", "id": chart3_id, "children": [],
    "parents": ["ROOT_ID", "GRID_ID", row2_id],
    "meta": {"width": 6, "height": 50, "chartId": 20, "sliceName": chart_names.get(20, "Flight Load Factor Summary")}
}
positions[chart4_id] = {
    "type": "CHART", "id": chart4_id, "children": [],
    "parents": ["ROOT_ID", "GRID_ID", row2_id],
    "meta": {"width": 6, "height": 50, "chartId": 21, "sliceName": chart_names.get(21, "Fare vs Load Factor Analysis")}
}
positions[row2_id] = {
    "type": "ROW", "id": row2_id,
    "children": [chart3_id, chart4_id],
    "parents": ["ROOT_ID", "GRID_ID"],
    "meta": {"background": "BACKGROUND_TRANSPARENT"}
}
grid_children.append(row2_id)

# Update grid
grid["children"] = grid_children
positions["GRID_ID"] = grid

# Save
cur.execute("UPDATE dashboards SET position_json = ? WHERE id = 1", (json.dumps(positions),))

# Also verify Dashboard #4 is gone
cur.execute("SELECT id FROM dashboards WHERE id = 4")
if cur.fetchone():
    cur.execute("DELETE FROM dashboard_slices WHERE dashboard_id = 4")
    cur.execute("DELETE FROM embedded_dashboards WHERE dashboard_id = 4")
    cur.execute("DELETE FROM dashboards WHERE id = 4")
    print("Deleted Dashboard #4")
else:
    print("Dashboard #4 already deleted")

# Final state
print()
print("=== Dashboard #1 Charts ===")
cur.execute("SELECT s.id, s.slice_name FROM dashboard_slices ds JOIN slices s ON s.id=ds.slice_id WHERE ds.dashboard_id=1 ORDER BY s.id")
for r in cur.fetchall():
    print(f"  Chart {r[0]}: {r[1]}")

print()
print("=== All Dashboards ===")
cur.execute("SELECT id, dashboard_title FROM dashboards ORDER BY id")
for r in cur.fetchall():
    print(f"  ID={r[0]}: {r[1]}")

conn.commit()
conn.close()
print("\nDone.")
