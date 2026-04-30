"""Ingestion Job tracking router — lists records from import_job and import_batch."""

import sys
import subprocess
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from app.core.deps import get_tenant_db, get_tenant_id, RequirePlatformAdmin
from app.models.ingestion import ImportJob, ImportBatch
from app.schemas.ingestion import (
    IngestionJobOut, ImportBatchOut, 
    PaginatedIngestionJobs, PageInfo
)

router = APIRouter(
    prefix="/api/v1/ingestion",
    tags=["ingestion"],
)


@router.get("/jobs", response_model=PaginatedIngestionJobs)
def list_jobs(
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
    domain: Optional[str] = None,
    status: Optional[str] = None,
    tenant: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """List all ingestion jobs for the current tenant context."""
    # RLS already handles the tenant_id filtering if configured on the DB side,
    # but we add an explicit check to be safe and consistent with the model.
    query = select(ImportJob).where(ImportJob.tenant_id == tenant_id)
    
    if domain:
        query = query.where(ImportJob.domain == domain)
    if status:
        query = query.where(ImportJob.status == status)
    if tenant:
        # In this app, 'data_owner' stores the tenant code (JY, PW, FJL)
        query = query.where(ImportJob.data_owner == tenant)
        
    # Count
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    # Sort and paginate
    jobs = db.scalars(
        query.order_by(desc(ImportJob.started_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    
    # Map to schema — the frontend expects 'tenant_code' which we store in 'data_owner'
    items = []
    for job in jobs:
        out = IngestionJobOut.model_validate(job)
        out.tenant_code = job.data_owner
        items.append(out)

    return {
        "items": items,
        "page_info": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages
        }
    }


@router.get("/jobs/{job_id}", response_model=IngestionJobOut)
def get_job_detail(
    job_id: str, 
    db: Session = Depends(get_tenant_db)
):
    """Get a detailed view of a single ingestion job."""
    job = db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    out = IngestionJobOut.model_validate(job)
    out.tenant_code = job.data_owner
    return out


@router.get("/jobs/{job_id}/batches", response_model=List[ImportBatchOut])
def list_job_batches(
    job_id: str, 
    db: Session = Depends(get_tenant_db)
):
    """List result batches for a specific job."""
    return db.scalars(select(ImportBatch).where(ImportBatch.import_job_id == job_id)).all()


@router.post("/ingest", dependencies=[Depends(RequirePlatformAdmin())])
def trigger_ingest_process(
    tenant: Optional[str] = None,
    force: bool = False,
    db: Session = Depends(get_tenant_db)
):
    """Trigger the daily CSV ingestion script as a background process."""
    cmd = [sys.executable, "scripts/ingest_daily.py"]
    if tenant:
        cmd.extend(["--tenant", tenant])
    if force:
        cmd.append("--force")
    
    try:
        # We run this synchronously for now to provide immediate feedback to the monitor
        # In a high-traffic system, this should be an async worker task (e.g. Celery)
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        import re as _re
        output = result.stdout or ""

        if result.returncode != 0:
            # Check for validation errors (date mismatch, missing files)
            for line in output.splitlines():
                if line.startswith("VALIDATION_ERROR:"):
                    error_msg = line.replace("VALIDATION_ERROR: ", "").strip()
                    error_msg = _re.sub(r"^\[.*?\]\s*", "", error_msg)
                    raise HTTPException(status_code=400, detail={"message": error_msg, "type": "validation_error"})
            return {"message": "Ingestion failed during processing", "error": result.stderr, "output": output}

        # Check for "already ingested" messages (not an error — just informational)
        for line in output.splitlines():
            if line.startswith("ALREADY_INGESTED:"):
                info_msg = line.replace("ALREADY_INGESTED: ", "").strip()
                info_msg = _re.sub(r"^\[.*?\]\s*", "", info_msg)
                return {"message": info_msg, "type": "already_ingested", "output": output}

        # Parse success details from output for richer response
        pricing_count = 0
        velocity_count = 0
        ingested_date = ""
        for line in output.splitlines():
            m = _re.search(r"\(pricing\) .+ → (\d+)/\d+ rows", line)
            if m:
                pricing_count = int(m.group(1))
            m = _re.search(r"\(velocity\) .+ → (\d+)/\d+ rows", line)
            if m:
                velocity_count = int(m.group(1))
            m = _re.search(r"ingested \d+ file\(s\) for date (\S+)", line)
            if m:
                ingested_date = m.group(1)

        if pricing_count or velocity_count:
            summary = f"Successfully ingested {pricing_count} pricing + {velocity_count} velocity records for date {ingested_date}."
            return {"message": summary, "type": "success", "output": output,
                    "details": {"pricing_records": pricing_count, "velocity_records": velocity_count, "date": ingested_date}}

        return {"message": "Ingestion task finished successfully", "output": output}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start ingestion script: {str(e)}")
