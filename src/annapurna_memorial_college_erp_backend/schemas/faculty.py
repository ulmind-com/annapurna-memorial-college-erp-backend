from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, EmailStr


class FacultyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ON_LEAVE = "ON_LEAVE"
    RESIGNED = "RESIGNED"


class FacultyBase(BaseModel):
    employee_id: str
    full_name: str
    email: EmailStr
    phone: str
    department: str
    designation: str
    qualification: str
    specialization: Optional[str] = None
    joining_date: Optional[str] = None
    assigned_subjects: List[str] = []
    status: FacultyStatus = FacultyStatus.ACTIVE
    avatar_url: Optional[str] = None


class FacultyCreate(FacultyBase):
    pass


class FacultyUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    qualification: Optional[str] = None
    specialization: Optional[str] = None
    assigned_subjects: Optional[List[str]] = None
    status: Optional[FacultyStatus] = None
    avatar_url: Optional[str] = None


class FacultyResponse(FacultyBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
