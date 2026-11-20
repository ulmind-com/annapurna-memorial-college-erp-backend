from typing import Optional, List, Dict, Any
from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, EmailStr


class StudentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    GRADUATED = "GRADUATED"
    DROPPED = "DROPPED"


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class StudentBase(BaseModel):
    roll_number: str
    registration_number: Optional[str] = None
    full_name: str
    email: EmailStr
    phone: str
    course_code: str
    course_name: Optional[str] = "Teacher Education Program"
    academic_session: Optional[str] = "2024-2026"
    semester: int = 1
    section: str = "A"
    date_of_birth: Optional[str] = None
    gender: Gender = Gender.MALE
    blood_group: Optional[str] = None
    category: str = "GEN"
    guardian_name: Optional[str] = "Guardian"
    guardian_phone: Optional[str] = "+91 9999999999"
    guardian_relation: str = "Father"
    address: Optional[str] = None
    status: StudentStatus = StudentStatus.ACTIVE
    avatar_url: Optional[str] = None


class StudentCreate(StudentBase):
    pass


class StudentUpdate(BaseModel):
    roll_number: Optional[str] = None
    registration_number: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    academic_session: Optional[str] = None
    semester: Optional[int] = None
    section: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[Gender] = None
    blood_group: Optional[str] = None
    category: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None
    guardian_relation: Optional[str] = None
    address: Optional[str] = None
    status: Optional[StudentStatus] = None
    avatar_url: Optional[str] = None


class StudentResponse(StudentBase):
    id: str
    documents: List[Dict[str, Any]] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
