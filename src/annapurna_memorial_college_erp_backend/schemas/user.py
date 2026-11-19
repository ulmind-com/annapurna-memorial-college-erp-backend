from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr
from annapurna_memorial_college_erp_backend.security import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole
    phone: Optional[str] = None
    is_active: bool = True
    entity_id: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    avatar_url: Optional[str] = None


class UserResponse(UserBase):
    id: str
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
