"""User-created alert rule instances — create / rename / delete / evaluate-load.

The first alerts tests in the repo. Mirrors the direct-handler-call convention
of tests/routers/test_price_points_availability.py: router handlers are invoked
against the transactional ``db_session`` fixture (all writes rolled back at
test end), no TestClient/HTTP layer. The test engine connects as the
RLS-bypassing superuser, so single-row lookups use minted instance keys (which
are unique across tenants by construction) and list assertions filter to the
DreamAir tenant's own rows.

Run ONLY this file (the full suite has known-unrelated failures), inside a
throwaway api container:
    pytest tests/routers/test_alert_rule_instances.py -q

Covers:
  a) LoadedRule.scoped(): identity for presets, rule_key prefix for instances
     — the no-re-fire invariant
  b) create: 201 shape, defaults merged, minted key, preset_key stamped
  c) create: unknown preset_key 422; missing-requirements activation 422
  d) rename: instance ok, built-in 400
  e) delete: instance row gone, built-in 400
  f) _ensure_presets: recreated preset rows carry preset_key; a deleted
     instance is NOT resurrected
  g) load_active_rules: instances load beside their preset, family-ordered,
     is_instance flagged
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.routers.alerts import (
    _ensure_presets, create_rule, delete_rule, update_rule,
)
from app.schemas.alerts import AlertRuleCreate, AlertRuleUpdate
from app.services.alerts.evaluator import LoadedRule, load_active_rules
from app.services.alerts.presets import PRESET_ORDER


@pytest.fixture
def da_tenant(db_session):
    """The DreamAir tenant UUID and an admin user of it."""
    row = db_session.execute(text(
        "SELECT t.id AS tid, u.id AS uid, u.email "
        "FROM tenant t JOIN app_user u ON u.tenant_id = t.id "
        "WHERE t.slug = 'da' LIMIT 1"
    )).first()
    if row is None:
        pytest.skip("DreamAir tenant/user not present in DB")
    return {
        "tenant_id": str(row.tid),
        "user": {"sub": str(row.uid), "email": row.email, "roles": ["TENANT_ADMIN"]},
    }


def _create(db, da, **overrides):
    body = AlertRuleCreate(**{
        "preset_key": "comp_price_move",
        "name": "My price watch",
        **overrides,
    })
    return create_rule(
        body, db=db, tenant_id=da["tenant_id"],
        current_user=da["user"], user_identity="DA",
    )


# ── a) the no-re-fire invariant ──────────────────────────────

def test_scoped_is_identity_for_presets():
    rule = LoadedRule(id="x", rule_key="comp_price_move",
                      preset_key="comp_price_move", name="n", severity="warning",
                      condition={}, is_instance=False)
    assert rule.scoped("move|AAA-BBB|XX|00-07") == "move|AAA-BBB|XX|00-07"


def test_scoped_prefixes_instances():
    rule = LoadedRule(id="x", rule_key="comp_price_move__ab12cd34",
                      preset_key="comp_price_move", name="n", severity="warning",
                      condition={}, is_instance=True)
    assert (rule.scoped("move|AAA-BBB|XX|00-07")
            == "comp_price_move__ab12cd34|move|AAA-BBB|XX|00-07")


# ── b/c) create ──────────────────────────────────────────────

def test_create_instance(db_session, da_tenant):
    out = _create(db_session, da_tenant, condition={"move_pct": 22.5})
    assert out.rule_key.startswith("comp_price_move__")
    assert out.preset_key == "comp_price_move"
    assert out.is_preset is False
    assert out.name == "My price watch"
    # Override applied over the family defaults, which fill everything else.
    assert out.condition["move_pct"] == 22.5
    assert "direction" in out.condition
    assert out.is_active is False
    assert out.tunables, "instances must render with their family's tunables"


def test_create_unknown_type_422(db_session, da_tenant):
    with pytest.raises(HTTPException) as e:
        _create(db_session, da_tenant, preset_key="not_a_rule")
    assert e.value.status_code == 422


def test_create_invalid_condition_422(db_session, da_tenant):
    with pytest.raises(HTTPException) as e:
        _create(db_session, da_tenant, condition={"no_such_field": 1})
    assert e.value.status_code == 422


def test_create_active_missing_requirements_422(db_session, da_tenant):
    # comp_price_threshold requires value + routes before it may be active.
    with pytest.raises(HTTPException) as e:
        _create(db_session, da_tenant,
                preset_key="comp_price_threshold", is_active=True)
    assert e.value.status_code == 422
    assert "missing" in e.value.detail


# ── d) rename ────────────────────────────────────────────────

def test_rename_instance(db_session, da_tenant):
    out = _create(db_session, da_tenant)
    renamed = update_rule(
        out.rule_key, AlertRuleUpdate(name="Sharper name"),
        db=db_session, tenant_id=da_tenant["tenant_id"],
        current_user=da_tenant["user"], user_identity="DA",
    )
    assert renamed.name == "Sharper name"


def test_rename_preset_400(db_session, da_tenant):
    _ensure_presets(db_session, da_tenant["tenant_id"])
    with pytest.raises(HTTPException) as e:
        update_rule(
            "comp_price_move", AlertRuleUpdate(name="nope"),
            db=db_session, tenant_id=da_tenant["tenant_id"],
            current_user=da_tenant["user"], user_identity="DA",
        )
    assert e.value.status_code == 400


# ── e) delete ────────────────────────────────────────────────

def test_delete_instance(db_session, da_tenant):
    out = _create(db_session, da_tenant)
    delete_rule(out.rule_key, db=db_session,
                tenant_id=da_tenant["tenant_id"], current_user=da_tenant["user"])
    left = db_session.execute(
        text("SELECT count(*) FROM alert_rule WHERE rule_key = :k"),
        {"k": out.rule_key}).scalar()
    assert left == 0


def test_delete_preset_400(db_session, da_tenant):
    _ensure_presets(db_session, da_tenant["tenant_id"])
    with pytest.raises(HTTPException) as e:
        delete_rule("comp_price_move", db=db_session,
                    tenant_id=da_tenant["tenant_id"],
                    current_user=da_tenant["user"])
    assert e.value.status_code == 400


# ── f) self-heal ─────────────────────────────────────────────

def test_ensure_presets_stamps_preset_key_and_skips_instances(db_session, da_tenant):
    tid = da_tenant["tenant_id"]
    # A deleted instance must stay deleted across the self-heal.
    out = _create(db_session, da_tenant)
    delete_rule(out.rule_key, db=db_session, tenant_id=tid,
                current_user=da_tenant["user"])
    # A deleted preset row must come back WITH its preset_key — without it the
    # evaluator's `preset_key IS NOT NULL` filter silently drops the rule.
    db_session.execute(text(
        "DELETE FROM alert_rule WHERE tenant_id = CAST(:t AS uuid) "
        "AND rule_key = 'comp_price_move'"), {"t": tid})
    _ensure_presets(db_session, tid)
    healed = db_session.execute(text(
        "SELECT preset_key FROM alert_rule WHERE tenant_id = CAST(:t AS uuid) "
        "AND rule_key = 'comp_price_move'"), {"t": tid}).scalar()
    assert healed == "comp_price_move"
    resurrected = db_session.execute(
        text("SELECT count(*) FROM alert_rule WHERE rule_key = :k"),
        {"k": out.rule_key}).scalar()
    assert resurrected == 0


# ── g) evaluator loading ─────────────────────────────────────

def test_load_active_rules_includes_instances(db_session, da_tenant):
    tid = da_tenant["tenant_id"]
    _ensure_presets(db_session, tid)
    out = _create(db_session, da_tenant, is_active=True,
                  condition={"move_pct": 5.0})
    rules = load_active_rules(db_session, tid)
    by_key = {r.rule_key: r for r in rules}
    assert out.rule_key in by_key, "active instance must load for evaluation"
    inst = by_key[out.rule_key]
    assert inst.is_instance is True
    assert inst.preset_key == "comp_price_move"
    assert inst.condition["move_pct"] == 5.0
    # Family-grouped ordering: the instance comes after its preset, and every
    # preset_key respects PRESET_ORDER.
    keys = [r.preset_key for r in rules]
    order = {k: i for i, k in enumerate(PRESET_ORDER)}
    assert keys == sorted(keys, key=lambda k: order.get(k, 99))
    if "comp_price_move" in by_key:
        assert (rules.index(by_key["comp_price_move"])
                < rules.index(inst)), "preset row precedes its instances"
