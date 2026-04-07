#!/usr/bin/env python3
"""Register velocity datasets, charts, and dashboard in Superset SQLite."""

import sqlite3
import json
import uuid
from datetime import datetime

DB_PATH = "/data/superset.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

# ── Check existing datasets ──────────────────────
cur.execute("SELECT id, table_name FROM tables WHERE table_name IN ('vw_jy_velocity_snapshot', 'vw_jy_fare_vs_load')")
existing = {row[1]: row[0] for row in cur.fetchall()}
print(f"Existing datasets: {existing}")

cur.execute("SELECT MAX(id) FROM tables")
max_id = cur.fetchone()[0] or 0

# ── Get admin user ID ────────────────────────────
cur.execute("SELECT id FROM ab_user WHERE username='admin' LIMIT 1")
admin_row = cur.fetchone()
admin_id = admin_row[0] if admin_row else 1

# ── Register vw_jy_velocity_snapshot ─────────────
vel_id = existing.get('vw_jy_velocity_snapshot')
if not vel_id:
    vel_id = max_id + 1
    cur.execute(
        "INSERT INTO tables (id, table_name, schema, database_id, is_sqllab_view, created_on, changed_on) VALUES (?, ?, 'public', 3, 0, ?, ?)",
        (vel_id, 'vw_jy_velocity_snapshot', now, now)
    )
    print(f"Registered vw_jy_velocity_snapshot as dataset ID={vel_id}")
else:
    print(f"vw_jy_velocity_snapshot already exists as ID={vel_id}")

# ── Register vw_jy_fare_vs_load ──────────────────
fvl_id = existing.get('vw_jy_fare_vs_load')
if not fvl_id:
    fvl_id = max_id + 2
    cur.execute(
        "INSERT INTO tables (id, table_name, schema, database_id, is_sqllab_view, created_on, changed_on) VALUES (?, ?, 'public', 3, 0, ?, ?)",
        (fvl_id, 'vw_jy_fare_vs_load', now, now)
    )
    print(f"Registered vw_jy_fare_vs_load as dataset ID={fvl_id}")
else:
    print(f"vw_jy_fare_vs_load already exists as ID={fvl_id}")

# ── Create Charts ────────────────────────────────
cur.execute("SELECT MAX(id) FROM slices")
slice_max = cur.fetchone()[0] or 0
sid = slice_max + 1

charts_created = []

# Chart 1: Seat Factor by Route
cur.execute(
    "INSERT INTO slices (id, slice_name, datasource_id, datasource_type, viz_type, params, created_on, changed_on, created_by_fk, changed_by_fk) VALUES (?, ?, ?, 'table', 'echarts_bar', ?, ?, ?, ?, ?)",
    (sid, 'Avg Seat Factor by Route', vel_id, json.dumps({
        'datasource': f'{vel_id}__table',
        'viz_type': 'echarts_bar',
        'x_axis': 'city_pair',
        'metrics': [{'label': 'Avg Seat Factor', 'expressionType': 'SQL', 'sqlExpression': 'AVG(actual_seat_factor)'}],
        'groupby': ['city_pair'],
        'adhoc_filters': [{'clause': 'WHERE', 'comparator': 'Segment', 'expressionType': 'SIMPLE', 'operator': '==', 'subject': 'legseg_type'}],
        'row_limit': 50,
        'order_desc': True,
    }), now, now, admin_id, admin_id)
)
charts_created.append((sid, 'Avg Seat Factor by Route'))
sid += 1

# Chart 2: Booking vs Capacity by Equipment
cur.execute(
    "INSERT INTO slices (id, slice_name, datasource_id, datasource_type, viz_type, params, created_on, changed_on, created_by_fk, changed_by_fk) VALUES (?, ?, ?, 'table', 'echarts_bar', ?, ?, ?, ?, ?)",
    (sid, 'Booking vs Capacity by Equipment', vel_id, json.dumps({
        'datasource': f'{vel_id}__table',
        'viz_type': 'echarts_bar',
        'x_axis': 'eqp',
        'metrics': [
            {'label': 'Total Bookings', 'expressionType': 'SQL', 'sqlExpression': 'SUM(current_booking)'},
            {'label': 'Total Capacity', 'expressionType': 'SQL', 'sqlExpression': 'SUM(capacity)'},
        ],
        'groupby': ['eqp'],
        'adhoc_filters': [{'clause': 'WHERE', 'comparator': 'Segment', 'expressionType': 'SIMPLE', 'operator': '==', 'subject': 'legseg_type'}],
        'row_limit': 50,
    }), now, now, admin_id, admin_id)
)
charts_created.append((sid, 'Booking vs Capacity by Equipment'))
sid += 1

# Chart 3: Flight Load Factor Summary
cur.execute(
    "INSERT INTO slices (id, slice_name, datasource_id, datasource_type, viz_type, params, created_on, changed_on, created_by_fk, changed_by_fk) VALUES (?, ?, ?, 'table', 'table', ?, ?, ?, ?, ?)",
    (sid, 'Flight Load Factor Summary', vel_id, json.dumps({
        'datasource': f'{vel_id}__table',
        'viz_type': 'table',
        'metrics': [
            {'label': 'Avg Seat Factor', 'expressionType': 'SQL', 'sqlExpression': 'ROUND(AVG(actual_seat_factor), 1)'},
            {'label': 'Min Seat Factor', 'expressionType': 'SQL', 'sqlExpression': 'MIN(actual_seat_factor)'},
            {'label': 'Max Seat Factor', 'expressionType': 'SQL', 'sqlExpression': 'MAX(actual_seat_factor)'},
            {'label': 'Total Flights', 'expressionType': 'SQL', 'sqlExpression': 'COUNT(*)'},
        ],
        'groupby': ['origin', 'destination', 'eqp'],
        'adhoc_filters': [{'clause': 'WHERE', 'comparator': 'Segment', 'expressionType': 'SIMPLE', 'operator': '==', 'subject': 'legseg_type'}],
        'order_desc': True,
        'row_limit': 100,
    }), now, now, admin_id, admin_id)
)
charts_created.append((sid, 'Flight Load Factor Summary'))
sid += 1

# Chart 4: Fare vs Load Factor
cur.execute(
    "INSERT INTO slices (id, slice_name, datasource_id, datasource_type, viz_type, params, created_on, changed_on, created_by_fk, changed_by_fk) VALUES (?, ?, ?, 'table', 'table', ?, ?, ?, ?, ?)",
    (sid, 'Fare vs Load Factor Analysis', fvl_id, json.dumps({
        'datasource': f'{fvl_id}__table',
        'viz_type': 'table',
        'all_columns': ['ref_flt_num', 'ref_org', 'ref_dst', 'ref_dep_date', 'ref_tot_fare', 'comp_tot_fare', 'fare_delta', 'actual_seat_factor', 'current_booking', 'capacity'],
        'order_desc': True,
        'row_limit': 100,
    }), now, now, admin_id, admin_id)
)
charts_created.append((sid, 'Fare vs Load Factor Analysis'))

# ── Create Dashboard ─────────────────────────────
cur.execute("SELECT MAX(id) FROM dashboards")
dash_max = cur.fetchone()[0] or 0
dash_id = dash_max + 1
dash_uuid = str(uuid.uuid4())

positions = {
    'DASHBOARD_VERSION_KEY': 'v2',
    'ROOT_ID': {'type': 'ROOT', 'id': 'ROOT_ID', 'children': ['GRID_ID']},
    'GRID_ID': {'type': 'GRID', 'id': 'GRID_ID', 'children': ['ROW-1', 'ROW-2'], 'parents': ['ROOT_ID']},
    'ROW-1': {'type': 'ROW', 'id': 'ROW-1', 'children': ['CHART-1', 'CHART-2'], 'parents': ['ROOT_ID', 'GRID_ID'], 'meta': {'background': 'BACKGROUND_TRANSPARENT'}},
    'ROW-2': {'type': 'ROW', 'id': 'ROW-2', 'children': ['CHART-3', 'CHART-4'], 'parents': ['ROOT_ID', 'GRID_ID'], 'meta': {'background': 'BACKGROUND_TRANSPARENT'}},
}
for i, (cid, cname) in enumerate(charts_created):
    key = f'CHART-{i+1}'
    positions[key] = {
        'type': 'CHART', 'id': key, 'children': [],
        'parents': ['ROOT_ID', 'GRID_ID', f'ROW-{(i // 2) + 1}'],
        'meta': {'width': 6, 'height': 50, 'chartId': cid, 'sliceName': cname}
    }

cur.execute(
    "INSERT INTO dashboards (id, dashboard_title, position_json, json_metadata, uuid, created_on, changed_on, created_by_fk, changed_by_fk, published) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
    (dash_id, 'JY Velocity & Load Factor', json.dumps(positions),
     json.dumps({'timed_refresh_immune_slices': [], 'expanded_slices': {}, 'refresh_frequency': 0, 'color_scheme': 'supersetColors'}),
     dash_uuid, now, now, admin_id, admin_id)
)

# Link charts to dashboard
for cid, _ in charts_created:
    cur.execute("INSERT OR IGNORE INTO dashboard_slices (dashboard_id, slice_id) VALUES (?, ?)", (dash_id, cid))

conn.commit()
conn.close()

print(f"Dashboard ID={dash_id}: 'JY Velocity & Load Factor' (uuid={dash_uuid})")
print(f"Charts: {charts_created}")
print(f"Datasets: velocity={vel_id}, fare_vs_load={fvl_id}")
print("Done.")
