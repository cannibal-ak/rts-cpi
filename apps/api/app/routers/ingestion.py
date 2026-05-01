"""Legacy ingestion router — folder-watch path retired in Phase A.

The folder-scanning ``ingest_daily.py`` script and the ``POST /ingest``
trigger have been removed. The new authenticated, audited, two-stage
upload pipeline lives at ``/api/v1/ingestion/upload`` etc. (see
``app/api/v1/ingestion.py``). This file is kept only so the old
``POST /api/v1/ingestion/ingest`` route returns a clear 410 Gone for any
remaining callers (the frontend "Ingest All" button is replaced cleanly
in Phase B). The whole file can be deleted once Phase B ships.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


@router.post("/ingest", include_in_schema=False)
def trigger_ingest_process_gone():
    """Folder-watch trigger has been retired."""
    raise HTTPException(
        status_code=410,
        detail={
            "error_code": "ingestion_legacy_endpoint_removed",
            "message": (
                "The folder-watch ingest trigger has been retired. "
                "Use the new upload flow at POST /api/v1/ingestion/upload "
                "(staged) followed by /validate and /commit."
            ),
        },
    )
