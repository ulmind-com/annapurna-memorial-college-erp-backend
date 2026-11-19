from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    ip_address: Optional[str] = None
    details: Dict[str, Any] = {}
    timestamp: datetime
