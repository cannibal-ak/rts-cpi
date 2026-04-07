import os
import sys

# Add superset to path
sys.path.append('/app')

from superset.app import create_app
from superset import db

app = create_app()

with app.app_context():
    from superset.models.dashboard import Dashboard
    from superset.models.embedded_dashboard import EmbeddedDashboard
    
    print("--- Dashboards ---")
    dashboards = db.session.query(Dashboard).all()
    for d in dashboards:
        print(f"ID: {d.id}, Title: {d.dashboard_title}, UUID: {d.uuid}")
        
    print("\n--- Embedded Dashboards ---")
    embedded = db.session.query(EmbeddedDashboard).all()
    for e in embedded:
        print(f"Dashboard ID: {e.dashboard_id}, Embedded UUID: {e.uuid}")

    print("\n--- Datasets ---")
    from superset.connectors.sqla.models import SqlaTable
    datasets = db.session.query(SqlaTable).all()
    for ds in datasets:
        print(f"ID: {ds.id}, Name: {ds.table_name}")
