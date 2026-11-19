from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    require_roles,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.audit import AuditLogResponse

router = APIRouter(prefix="/audit", tags=["Security Audit Logs"])


@router.get("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def list_audit_logs(
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_email: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    db = await get_db()
    query = {}
    if action:
        query["action"] = action
    if entity_type:
        query["entity_type"] = entity_type
    if user_email:
        query["user_email"] = {"$regex": user_email, "$options": "i"}

    total = await db.audit_logs.count_documents(query)
    cursor = db.audit_logs.find(query).skip((page - 1) * limit).limit(limit).sort("timestamp", -1)
    logs = []
    async for l in cursor:
        logs.append({
            "id": str(l["_id"]),
            "user_id": l.get("user_id"),
            "user_email": l.get("user_email"),
            "user_role": l.get("user_role"),
            "action": l["action"],
            "entity_type": l["entity_type"],
            "entity_id": l.get("entity_id"),
            "ip_address": l.get("ip_address"),
            "details": l.get("details", {}),
            "timestamp": l["timestamp"],
        })

    return {
        "items": logs,
        "total": total,
        "page": page,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
    }
