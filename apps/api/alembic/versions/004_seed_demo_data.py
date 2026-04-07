"""Seed minimal demo data for 2 tenants + sample snapshots.

Tenant A: "Acme Airways" — airline-focused
Tenant B: "Baltic Ferries" — CFL-focused (has both modules)

Revision ID: 004
Revises: 003
Create Date: 2026-03-05
"""
from typing import Sequence, Union
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_A = "a0000000-0000-0000-0000-000000000001"
TENANT_B = "b0000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    # ════════════════════════════════════════════════
    # TENANTS
    # ════════════════════════════════════════════════
    op.execute(f"""
        INSERT INTO tenant (id, slug, display_name) VALUES
        ('{TENANT_A}', 'acme-airways', 'Acme Airways'),
        ('{TENANT_B}', 'baltic-ferries', 'Baltic Ferries');
    """)

    # ════════════════════════════════════════════════
    # TENANT FEATURES
    # ════════════════════════════════════════════════
    features = [
        ("airline", "Airline Module", "module"),
        ("cfl", "CFL Module", "module"),
        ("alerts", "Alerting", "capability"),
        ("exports", "CSV / Excel Export", "capability"),
        ("audit", "Audit Log", "capability"),
        ("saved_views", "Saved Views", "capability"),
        ("contracts", "Contract Overlays", "capability"),
        ("superset_embed", "Superset Dashboards", "analytics"),
        ("anomaly_detection", "AI Anomaly Detection", "analytics"),
        ("custom_branding", "Custom Branding", "branding"),
    ]

    # Tenant A: airline-focused (airline on, cfl off)
    for code, label, cat in features:
        enabled = "true" if code not in ("cfl", "anomaly_detection", "custom_branding") else "false"
        op.execute(f"""
            INSERT INTO tenant_feature (tenant_id, code, label, category, enabled)
            VALUES ('{TENANT_A}', '{code}', '{label}', '{cat}', {enabled});
        """)

    # Tenant B: both modules
    for code, label, cat in features:
        enabled = "true" if code not in ("anomaly_detection", "custom_branding") else "false"
        op.execute(f"""
            INSERT INTO tenant_feature (tenant_id, code, label, category, enabled)
            VALUES ('{TENANT_B}', '{code}', '{label}', '{cat}', {enabled});
        """)

    # ════════════════════════════════════════════════
    # USERS + ROLES
    # ════════════════════════════════════════════════
    user_a1 = "aa100000-0000-0000-0000-000000000001"
    user_a2 = "aa200000-0000-0000-0000-000000000002"
    user_b1 = "bb100000-0000-0000-0000-000000000001"
    user_b2 = "bb200000-0000-0000-0000-000000000002"

    op.execute(f"""
        INSERT INTO app_user (id, tenant_id, email, display_name) VALUES
        ('{user_a1}', '{TENANT_A}', 'admin@acme-airways.com', 'Alice Admin'),
        ('{user_a2}', '{TENANT_A}', 'analyst@acme-airways.com', 'Bob Analyst'),
        ('{user_b1}', '{TENANT_B}', 'admin@baltic-ferries.com', 'Carol Admin'),
        ('{user_b2}', '{TENANT_B}', 'engineer@baltic-ferries.com', 'Dave Engineer');
    """)

    op.execute(f"""
        INSERT INTO role_binding (tenant_id, user_id, role) VALUES
        ('{TENANT_A}', '{user_a1}', 'TENANT_ADMIN'),
        ('{TENANT_A}', '{user_a2}', 'ANALYST'),
        ('{TENANT_B}', '{user_b1}', 'TENANT_ADMIN'),
        ('{TENANT_B}', '{user_b2}', 'DATA_ENGINEER');
    """)

    # ════════════════════════════════════════════════
    # SOURCE SYSTEMS
    # ════════════════════════════════════════════════
    src_a1 = "ca100000-0000-0000-0000-000000000001"
    src_b1 = "cb100000-0000-0000-0000-000000000001"

    op.execute(f"""
        INSERT INTO source_system (id, tenant_id, code, display_name, domain) VALUES
        ('{src_a1}', '{TENANT_A}', 'local-airline', 'Local Folder - Airline', 'airline'),
        ('{src_b1}', '{TENANT_B}', 'local-cfl', 'Local Folder - CFL', 'cfl');
    """)

    # ════════════════════════════════════════════════
    # AIRLINE CPI SNAPSHOTS (REMOVED SEEDING)
    # ════════════════════════════════════════════════

    # ════════════════════════════════════════════════
    # CFL CPI SNAPSHOTS (REMOVED SEEDING)
    # ════════════════════════════════════════════════

    # ════════════════════════════════════════════════
    # ALERT RULES + EVENTS
    # ════════════════════════════════════════════════
    rule_a1 = "fa100000-0000-0000-0000-000000000001"
    rule_a2 = "fa200000-0000-0000-0000-000000000002"
    rule_b1 = "fb100000-0000-0000-0000-000000000001"

    op.execute(f"""
        INSERT INTO alert_rule (id, tenant_id, name, domain, rule_type, condition_json, owner) VALUES
        ('{rule_a1}', '{TENANT_A}', 'Fare drop > 15%', 'airline', 'threshold',
         '{{"field": "comp_tot_fare", "operator": "decrease_pct", "value": 15}}', 'admin@acme-airways.com'),
        ('{rule_a2}', '{TENANT_A}', 'New competitor route detected', 'airline', 'anomaly',
         '{{"detect": "new_route_pair"}}', 'analyst@acme-airways.com'),
        ('{rule_b1}', '{TENANT_B}', 'CFL price spike > 20%', 'cfl', 'threshold',
         '{{"field": "total_fare", "operator": "increase_pct", "value": 20}}', 'admin@baltic-ferries.com');
    """)

    # ════════════════════════════════════════════════
    # PROVIDER CONTRACTS
    # ════════════════════════════════════════════════
    op.execute(f"""
        INSERT INTO provider_contract (tenant_id, name, provider, domain, status, validation_mode,
                                       field_mappings, required_fields, optional_fields) VALUES
        ('{TENANT_A}', 'BA Standard v2', 'British Airways', 'airline', 'active', 'STRICT',
         '{{"fare": "ref_tot_fare", "airline_code": "ref_al"}}',
         '["ref_al","ref_org","ref_dst","ref_tot_fare"]',
         '["ref_yq","ref_seats"]'),
        ('{TENANT_A}', 'Emirates Draft', 'Emirates', 'airline', 'draft', 'STRICT',
         '{{}}', '[]', '[]'),
        ('{TENANT_B}', 'DFDS Ferry Compat', 'DFDS', 'cfl', 'active', 'COMPAT',
         '{{"price": "total_fare", "operator": "source"}}',
         '["source","org","dest","total_fare"]',
         '["out_cab_type","veh_size"]'),
        ('{TENANT_B}', 'Stena Legacy', 'Stena Line', 'cfl', 'deprecated', 'COMPAT',
         '{{"price": "total_fare"}}',
         '["source","org","dest"]', '[]');
    """)

    # ════════════════════════════════════════════════
    # AUDIT EVENTS (REMOVED SEEDING)
    # ════════════════════════════════════════════════

    # ════════════════════════════════════════════════
    # API CLIENTS (for testing)
    # ════════════════════════════════════════════════
    op.execute(f"""
        INSERT INTO api_client (tenant_id, client_name, client_key, hashed_secret, scopes) VALUES
        ('{TENANT_A}', 'Acme Dev Client', 'acme-dev-key', 'hashed_placeholder', '["read","write"]'),
        ('{TENANT_B}', 'Baltic Dev Client', 'baltic-dev-key', 'hashed_placeholder', '["read","write"]');
    """)



def downgrade() -> None:
    # Delete in reverse order to respect FKs
    op.execute(f"DELETE FROM api_client WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM audit_event WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM alert_event WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM alert_rule WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM provider_contract WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM cfl_cpi_snapshot WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM airline_cpi_snapshot WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM ingest_error WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM import_batch WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM import_job WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM source_system WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM role_binding WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM app_user WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM tenant_feature WHERE tenant_id IN ('{TENANT_A}', '{TENANT_B}');")
    op.execute(f"DELETE FROM tenant WHERE id IN ('{TENANT_A}', '{TENANT_B}');")
