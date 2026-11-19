from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any
from enum import Enum
import bcrypt
import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from annapurna_memorial_college_erp_backend.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)


class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    FACULTY = "FACULTY"
    STUDENT = "STUDENT"
    STAFF = "STAFF"


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please re-authenticate.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    user_id = payload.get("sub")
    role = payload.get("role")
    email = payload.get("email")
    if user_id is None or role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "id": user_id,
        "email": email,
        "role": role,
        "name": payload.get("name", ""),
        "entity_id": payload.get("entity_id", None),
    }


def require_roles(allowed_roles: List[UserRole]):
    def role_checker(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role")
        role_values = [r.value if isinstance(r, UserRole) else r for r in allowed_roles]
        if user_role not in role_values and user_role != UserRole.SUPER_ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires one of {role_values}",
            )
        return current_user
    return role_checker
