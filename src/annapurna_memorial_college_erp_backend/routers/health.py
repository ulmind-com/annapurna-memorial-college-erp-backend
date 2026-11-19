from datetime import datetime, timezone
from fastapi import APIRouter
from annapurna_memorial_college_erp_backend.config import settings
from annapurna_memorial_college_erp_backend.database import DatabaseManager

router = APIRouter(tags=["Health & System"])


@router.get("/health")
async def health_check():
    db_status = "connected"
    try:
        if DatabaseManager.client:
            await DatabaseManager.client.admin.command("ping")
        else:
            db_status = "uninitialized"
    except Exception as e:
        db_status = f"degraded ({str(e)})"

    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "college": settings.COLLEGE_LEGAL_NAME,
        "version": settings.VERSION,
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
