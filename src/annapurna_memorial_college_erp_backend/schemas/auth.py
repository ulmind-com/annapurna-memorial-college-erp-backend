from typing import Optional
from pydantic import BaseModel, EmailStr
from annapurna_memorial_college_erp_backend.security import UserRole


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
