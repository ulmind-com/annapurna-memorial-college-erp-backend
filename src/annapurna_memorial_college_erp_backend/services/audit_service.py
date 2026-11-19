import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from annapurna_memorial_college_erp_backend.database import get_db

logger = logging.getLogger("erp.audit")


class AuditService:
    @staticmethod
    async def log_action(
        action: str,
        entity_type: str,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        user_role: Optional[str] = None,
        entity_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        try:
            db = await get_db()
            entry = {
                "action": action,
                "entity_type": entity_type,
                "user_id": user_id,
                "user_email": user_email,
                "user_role": user_role,
                "entity_id": entity_id,
                "ip_address": ip_address,
                "details": details or {},
                "timestamp": datetime.now(timezone.utc),
            }
            await db.audit_logs.insert_one(entry)
        except Exception as e:
            logger.warning(f"Failed to record audit log: {e}")


audit_service = AuditService()
