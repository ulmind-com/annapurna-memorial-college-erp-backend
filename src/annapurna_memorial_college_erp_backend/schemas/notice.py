from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class NoticeCategory(str, Enum):
    ACADEMIC = "ACADEMIC"
    EXAMINATION = "EXAMINATION"
    ADMISSION = "ADMISSION"
    EVENT = "EVENT"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    EMERGENCY = "EMERGENCY"


class TargetAudience(str, Enum):
    ALL = "ALL"
    STUDENTS = "STUDENTS"
    FACULTY = "FACULTY"
    STAFF = "STAFF"


class NoticePriority(str, Enum):
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class NoticeBase(BaseModel):
    title: str
    content: str
    category: NoticeCategory = NoticeCategory.ACADEMIC
    target_audience: TargetAudience = TargetAudience.ALL
    priority: NoticePriority = NoticePriority.NORMAL
    is_pinned: bool = False
    attachment_url: Optional[str] = None
    send_email: bool = False
    send_push: bool = False


class NoticeCreate(NoticeBase):
    pass


class NoticeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[NoticeCategory] = None
    target_audience: Optional[TargetAudience] = None
    priority: Optional[NoticePriority] = None
    is_pinned: Optional[bool] = None
    attachment_url: Optional[str] = None


class NoticeResponse(NoticeBase):
    id: str
    published_by_id: str
    published_by_name: str
    views_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
