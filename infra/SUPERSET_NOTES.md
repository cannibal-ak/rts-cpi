# Superset runtime state notes

The Superset container (`cpi-superset-1`) uses a **SQLite metadata DB** at
`/app/superset_home/superset.db`, persisted to the `superset_home` named
volume.  That DB is **not in git** — anything you change there (roles,
permissions, datasets, dashboards) must be re-applied after a clean
volume rebuild or a fresh checkout on a new host.

This file documents the manual one-off changes the runtime depends on
beyond `infra/superset_config.py`.

## Public role — chart-view access (2026-05-14)

The "Chart view" mode in the dashboard page embeds individual charts via
the standalone explore URL (`/explore/?slice_id=X&standalone=1`).  That
endpoint runs unauthenticated — `PUBLIC_ROLE_LIKE = "Gamma"` in
`superset_config.py` already sets the Public role up with read-y
permissions, but **Gamma deliberately does not include datasource
access** in Superset, so anonymous chart fetches fail with:

    This endpoint requires the datasource public.vw_…, database
    or `all_datasource_access` permission

### Required state on the Public role

| Permission                | View menu                  | Granted? | Why |
| ------------------------- | -------------------------- | -------- | --- |
| `all_datasource_access`   | `all_datasource_access`    | YES      | lets anonymous /explore queries run |
| `can_write` / `can_add` / `can_edit` / `can_delete` on anything | n/a | **NO** | read-only; chart view never needs to write |

### Re-apply (run inside `cpi-superset-1`)

```python
import sqlite3
c = sqlite3.connect("/app/superset_home/superset.db").cursor()
c.execute("SELECT id FROM ab_role WHERE name='Public'")
pid = c.fetchone()[0]

# 1. GRANT all_datasource_access
c.execute("SELECT pv.id FROM ab_permission_view pv "
          "JOIN ab_permission p ON p.id=pv.permission_id "
          "WHERE p.name='all_datasource_access'")
pv_id = c.fetchone()[0]
c.execute("INSERT OR IGNORE INTO ab_permission_view_role "
          "(permission_view_id, role_id) VALUES (?, ?)", (pv_id, pid))

# 2. REVOKE every write-class perm Gamma inherited to Public
c.execute("""
    DELETE FROM ab_permission_view_role
    WHERE id IN (
      SELECT pvr.id FROM ab_permission_view_role pvr
      JOIN ab_permission_view pv ON pv.id = pvr.permission_view_id
      JOIN ab_permission p ON p.id = pv.permission_id
      WHERE pvr.role_id = ?
        AND p.name IN ('can_write','can_add','can_edit','can_delete')
    )
""", (pid,))

c.connection.commit()
```

Then `docker compose restart superset` to flush the permission cache.

### Why this isn't in `superset_config.py`

Permissions live in the metadata DB and FAB doesn't auto-revoke perms on
restart — `PUBLIC_ROLE_LIKE` only **adds** Gamma's perms to Public, it
never trims.  So the revoke step has to run against the DB directly.
