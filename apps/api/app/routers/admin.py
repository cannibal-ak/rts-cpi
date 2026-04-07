"""Admin endpoints — tenant features, provider contracts, and source config (DB queries)."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.deps import get_tenant_db, get_tenant_id, RequireRoles
from app.models.admin import ProviderContract
from app.models.tenant_feature import TenantFeature
from app.schemas.admin import (
    TenantFeatureOut, TenantFeatureUpdate,
    ProviderContractOut, ProviderContractCreate,
)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(RequireRoles("TENANT_ADMIN", "DATA_ENGINEER", "ANALYST", "REVENUE_MANAGER", "AUDITOR"))]
)


# ── Tenant Features ───────────────────────────
@router.get(
    "/tenant/features",
    response_model=list[TenantFeatureOut],
    dependencies=[Depends(RequireRoles("TENANT_ADMIN"))],
)
def get_tenant_features(db: Session = Depends(get_tenant_db)):
    return db.scalars(select(TenantFeature)).all()


@router.patch(
    "/tenant/features/{code}",
    response_model=TenantFeatureOut,
    dependencies=[Depends(RequireRoles("TENANT_ADMIN"))],
)
def set_tenant_feature(code: str, body: TenantFeatureUpdate, db: Session = Depends(get_tenant_db)):
    feat = db.scalars(select(TenantFeature).where(TenantFeature.code == code)).first()
    if not feat:
        raise HTTPException(status_code=404, detail="Feature not found")
    feat.enabled = body.enabled
    db.commit()
    db.refresh(feat)
    return feat


# ── Provider Contracts ────────────────────────
@router.get("/contracts", response_model=list[ProviderContractOut])
def list_contracts(db: Session = Depends(get_tenant_db)):
    return db.scalars(select(ProviderContract)).all()


@router.post(
    "/contracts",
    response_model=ProviderContractOut,
    status_code=201,
    dependencies=[Depends(RequireRoles("TENANT_ADMIN"))],
)
def create_contract(
    body: ProviderContractCreate,
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
):
    contract = ProviderContract(
        tenant_id=tenant_id,
        name=body.name, provider=body.provider, domain=body.domain,
        status=body.status, validation_mode=body.validation_mode,
        field_mappings=body.field_mappings,
        required_fields=body.required_fields,
        optional_fields=body.optional_fields,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract


@router.put(
    "/contracts/{contract_id}",
    response_model=ProviderContractOut,
    dependencies=[Depends(RequireRoles("TENANT_ADMIN"))],
)
def update_contract(contract_id: str, body: ProviderContractCreate, db: Session = Depends(get_tenant_db)):
    c = db.get(ProviderContract, contract_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contract not found")
    c.name = body.name
    c.provider = body.provider
    c.domain = body.domain
    c.validation_mode = body.validation_mode
    c.field_mappings = body.field_mappings
    c.required_fields = body.required_fields
    c.optional_fields = body.optional_fields
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(c)
    return c


@router.post(
    "/contracts/{contract_id}/activate",
    response_model=ProviderContractOut,
    dependencies=[Depends(RequireRoles("TENANT_ADMIN"))],
)
def activate_contract(contract_id: str, db: Session = Depends(get_tenant_db)):
    c = db.get(ProviderContract, contract_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contract not found")
    if c.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft contracts can be activated")
    c.status = "active"
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(c)
    return c


@router.post(
    "/contracts/{contract_id}/deprecate",
    response_model=ProviderContractOut,
    dependencies=[Depends(RequireRoles("TENANT_ADMIN"))],
)
def deprecate_contract(contract_id: str, db: Session = Depends(get_tenant_db)):
    c = db.get(ProviderContract, contract_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contract not found")
    if c.status != "active":
        raise HTTPException(status_code=400, detail="Only active contracts can be deprecated")
    c.status = "deprecated"
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(c)
    return c
