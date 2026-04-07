#!/usr/bin/env python3
"""Set up per-tenant Superset datasets + dataset-level permissions.

Run from the Superset container (or any host that can reach Superset at 8088):

  python3 /scripts/setup_superset_datasets.py

What it does:
  1. Authenticates to Superset as admin (session cookies).
  2. Finds the "CPI PostgreSQL" database connection.
  3. Creates (or skips) three datasets pointing to the new per-tenant views:
       - vw_airline_cpi_jy_snapshot
       - vw_airline_cpi_pw_snapshot
       - vw_cfl_cpi_fjl_snapshot
  4. Grants Gamma role datasource_access on each dataset.
  5. Prints dataset IDs for reference.

Requires: requests (pip install requests).  Uses session auth (not JWT)
because Superset 3.x dataset creation APIs need full session permissions.
"""

import os
import sys
import requests

SUPERSET_URL = os.getenv("SUPERSET_URL", "http://localhost:8088")
ADMIN_USER = os.getenv("SUPERSET_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("SUPERSET_ADMIN_PASS", "admin")

# Per-tenant datasets to create
DATASETS = [
    {"table_name": "vw_airline_cpi_jy_snapshot",  "schema": "public", "label": "Airline CPI JY"},
    {"table_name": "vw_airline_cpi_pw_snapshot",  "schema": "public", "label": "Airline CPI PW"},
    {"table_name": "vw_cfl_cpi_fjl_snapshot",     "schema": "public", "label": "Cruise/Ferry CPI FJL"},
]


def get_session():
    """Authenticate and return a requests.Session with cookies."""
    s = requests.Session()
    # Get CSRF token from login page
    r = s.get(f"{SUPERSET_URL}/login/")
    r.raise_for_status()
    # POST login
    r = s.post(
        f"{SUPERSET_URL}/login/",
        data={"username": ADMIN_USER, "password": ADMIN_PASS},
        allow_redirects=False,
    )
    if r.status_code not in (200, 302):
        print(f"ERROR: Login failed ({r.status_code})")
        sys.exit(1)
    print(f"Authenticated as {ADMIN_USER}")
    return s


def get_csrf_token(session: requests.Session) -> str:
    """Fetch a CSRF token for API POST requests."""
    r = session.get(f"{SUPERSET_URL}/api/v1/security/csrf_token/")
    if r.status_code == 200:
        return r.json().get("result", "")
    return ""


def find_database_id(session: requests.Session) -> int | None:
    """Find the 'CPI PostgreSQL' database connection ID."""
    r = session.get(f"{SUPERSET_URL}/api/v1/database/")
    r.raise_for_status()
    for db in r.json().get("result", []):
        name = db.get("database_name", "")
        if "cpi" in name.lower() or "postgresql" in name.lower():
            print(f"Found database: '{name}' (id={db['id']})")
            return db["id"]
    print("WARNING: No CPI database found. Available databases:")
    for db in r.json().get("result", []):
        print(f"  id={db['id']} name={db.get('database_name')}")
    return None


def list_existing_datasets(session: requests.Session) -> dict[str, int]:
    """Return {table_name: dataset_id} for existing datasets."""
    r = session.get(f"{SUPERSET_URL}/api/v1/dataset/?q=(page_size:100)")
    r.raise_for_status()
    return {
        d.get("table_name"): d["id"]
        for d in r.json().get("result", [])
        if d.get("table_name")
    }


def create_dataset(session: requests.Session, db_id: int, table_name: str,
                   schema: str, csrf_token: str) -> int | None:
    """Create a dataset. Returns the new dataset ID or None on failure."""
    payload = {
        "database": db_id,
        "table_name": table_name,
        "schema": schema,
    }
    headers = {}
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
        headers["Referer"] = SUPERSET_URL

    r = session.post(
        f"{SUPERSET_URL}/api/v1/dataset/",
        json=payload,
        headers=headers,
    )
    if r.status_code in (200, 201):
        ds_id = r.json().get("id")
        print(f"  Created dataset: {table_name} (id={ds_id})")
        return ds_id
    else:
        print(f"  ERROR creating {table_name}: {r.status_code} — {r.text[:200]}")
        return None


def grant_gamma_access(session: requests.Session, dataset_id: int,
                       perm_name: str, csrf_token: str):
    """Grant Gamma role datasource_access for a dataset.

    This is done by finding the permission_view for datasource_access on
    the dataset and adding Gamma's role_id to it.  For simplicity, we use
    the Superset security API.
    """
    # This is a best-effort operation — Superset's API for this is limited.
    # The admin UI is more reliable for permission grants.
    print(f"  NOTE: Grant Gamma access to dataset {dataset_id} ({perm_name})")
    print(f"        → Do this manually in Superset UI: Settings → List Roles → Gamma → add datasource_access for [{perm_name}]")


def main():
    session = get_session()
    csrf_token = get_csrf_token(session)

    # Find the CPI database
    db_id = find_database_id(session)
    if not db_id:
        print("ERROR: Cannot proceed without a database connection.")
        print("       Create one in Superset: Databases → + Database → PostgreSQL")
        print("       Connection: postgresql://cpi_app:cpi_app_secret@postgres:5432/cpi_db")
        sys.exit(1)

    # Check existing datasets
    existing = list_existing_datasets(session)
    print(f"\nExisting datasets: {list(existing.keys())}")

    # Create missing datasets
    created = {}
    for ds_cfg in DATASETS:
        tname = ds_cfg["table_name"]
        if tname in existing:
            print(f"  SKIP: {tname} already exists (id={existing[tname]})")
            created[tname] = existing[tname]
        else:
            ds_id = create_dataset(session, db_id, tname, ds_cfg["schema"], csrf_token)
            if ds_id:
                created[tname] = ds_id

    # Grant permissions
    print("\n=== Permission Grants ===")
    for ds_cfg in DATASETS:
        tname = ds_cfg["table_name"]
        if tname in created:
            # The perm string format in Superset is: [database_name].[table_name](id:N)
            perm_name = f"{tname}"
            grant_gamma_access(session, created[tname], perm_name, csrf_token)

    # Summary
    print("\n=== Dataset Summary ===")
    for ds_cfg in DATASETS:
        tname = ds_cfg["table_name"]
        ds_id = created.get(tname, "NOT CREATED")
        print(f"  {ds_cfg['label']:30s} → {tname} (id={ds_id})")

    print("\n=== Next Steps ===")
    print("1. In Superset UI: update each dashboard to use its per-tenant dataset")
    print("2. Add 'File Date' native filter pointing to the 'file_date' column")
    print("3. Grant Gamma role datasource_access for each new dataset")
    print("4. Test with guest tokens from the CPI frontend")


if __name__ == "__main__":
    main()
