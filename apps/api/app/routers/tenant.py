"""Tenant (User Roles) Endpoints."""

from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from app.core.config import settings
from app.core.deps import get_tenant_db, get_tenant_id, RequireRoles
from app.models.user import AppUser, RoleBinding
from pydantic import BaseModel
from typing import List

router = APIRouter(
    prefix="/api/v1/tenant",
    tags=["tenant"],
    dependencies=[Depends(RequireRoles("TENANT_ADMIN", "DATA_ENGINEER", "ANALYST", "REVENUE_MANAGER", "AUDITOR"))]
)

class RolesUpdate(BaseModel):
    tenant_id: str
    roles: List[str]

class UserRolesResponse(BaseModel):
    roles: List[str]

@router.get("/user-roles", response_model=UserRolesResponse)
def get_user_roles(db: Session = Depends(get_tenant_db), tenant_id: str = Depends(get_tenant_id)):
    """Return distinct roles for the tenant.
    In this demo/headless mode, we return all distinct roles assigned to any user
    in this tenant to ensure the UI can show/toggle them all and doesn't get locked out.
    """
    tenant_uuid = uuid.UUID(tenant_id)
    
    # Get all distinct roles for this tenant
    roles = db.scalars(
        select(RoleBinding.role)
        .where(RoleBinding.tenant_id == tenant_uuid)
        .distinct()
    ).all()
    
    # If no users/roles exist yet, ensure at least one user exists and give them TENANT_ADMIN
    if not roles:
        user = db.scalars(select(AppUser).where(AppUser.tenant_id == tenant_uuid)).first()
        if not user:
            user = AppUser(
                tenant_id=tenant_uuid,
                email="admin@rts.local",
                display_name="Demo User"
            )
            db.add(user)
            db.flush() # get user.id

        default_binding = RoleBinding(tenant_id=tenant_uuid, user_id=user.id, role="TENANT_ADMIN")
        db.add(default_binding)
        db.commit()
        roles = ["TENANT_ADMIN"]

    return {"roles": list(roles)}

@router.post("/update-roles", response_model=UserRolesResponse)
def update_user_roles(
    body: RolesUpdate,
    db: Session = Depends(get_tenant_db),
    tenant_id_dep: str = Depends(get_tenant_id)
):
    """Update roles for the tenant's user.
    Uses the tenant ID from the X-Tenant-ID header (sanitized by get_tenant_db) 
    to ensure RLS and isolation are respected even if the body ID is mock/incorrect.
    """
    try:
        # Prioritize the reliable tenant_id from our dependency/context
        tenant_uuid = uuid.UUID(tenant_id_dep)
    except ValueError:
        # Fallback to body only if header is somehow missing (impossible with our middleware but for safety)
        try:
            tenant_uuid = uuid.UUID(body.tenant_id)
        except ValueError:
            # If both are invalid/mock, we use the default fallback
            tenant_uuid = uuid.UUID(settings.default_tenant_id)

    # Use the email from the demo system or header logic
    # In a real app we'd use the current logged-in user's ID
    user = db.scalars(select(AppUser).where(AppUser.tenant_id == tenant_uuid)).first()
    
    if not user:
        # Create a user if none exists for this tenant
        user = AppUser(
            tenant_id=tenant_uuid,
            email="admin@rts.local", # demo default
            display_name="Demo User"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    try:
        # Delete existing roles for this user
        db.execute(delete(RoleBinding).where(RoleBinding.user_id == user.id, RoleBinding.tenant_id == tenant_uuid))
        
        # Insert requested roles
        valid_roles = {"TENANT_ADMIN", "DATA_ENGINEER", "ANALYST", "REVENUE_MANAGER", "AUDITOR"}
        added_roles = []
        for role_name in body.roles:
            role_upper = role_name.upper().strip()
            if role_upper in valid_roles:
                rb = RoleBinding(tenant_id=tenant_uuid, user_id=user.id, role=role_upper)
                db.add(rb)
                added_roles.append(role_upper)
            
        db.commit()
        return {"roles": added_roles}

    except Exception as e:
        db.rollback()
        import sys
        print(f"CRITICAL ERROR in update_user_roles: {str(e)}", file=sys.stderr)
        # Detailed error for the client during dev
        raise HTTPException(status_code=500, detail=f"Database persistent failure: {str(e)}")
