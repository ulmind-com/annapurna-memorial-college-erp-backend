from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from annapurna_memorial_college_erp_backend.config import settings
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    require_roles,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    ChangePasswordRequest,
)
from annapurna_memorial_college_erp_backend.services.email_service import email_service
from annapurna_memorial_college_erp_backend.services.audit_service import audit_service

from annapurna_memorial_college_erp_backend.validators import check_email_format, find_email_owner, EmailProblem

router = APIRouter(prefix="/auth", tags=["Authentication & Security"])

# High-tolerance sliding-window lockout protection: prevents automated attacks without locking out testing users
FAILED_ATTEMPTS: dict[str, list[datetime]] = {}
MAX_FAILED_ATTEMPTS = 50
LOCKOUT_MINUTES = 2


def check_brute_force(key: str):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
    attempts = [t for t in FAILED_ATTEMPTS.get(key, []) if t > cutoff]
    FAILED_ATTEMPTS[key] = attempts
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        first_attempt = attempts[0]
        remaining_seconds = int((first_attempt + timedelta(minutes=LOCKOUT_MINUTES) - now).total_seconds())
        remaining_seconds = max(remaining_seconds, 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Security Lockout: 5 failed login attempts detected. Please wait {remaining_seconds} seconds before attempting again.",
        )


def record_failed_attempt(key: str):
    now = datetime.now(timezone.utc)
    if key not in FAILED_ATTEMPTS:
        FAILED_ATTEMPTS[key] = []
    FAILED_ATTEMPTS[key].append(now)


def reset_failed_attempts(key: str):
    FAILED_ATTEMPTS.pop(key, None)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    clean_email = req.email.strip().lower()
    client_ip = request.client.host if request.client else "127.0.0.1"
    throttle_key = f"{clean_email}_{client_ip}"

    # Verify brute-force lockout status
    check_brute_force(throttle_key)

    db = await get_db()
    user = await db.users.find_one({"email": clean_email})

    # One-time bootstrap: create the default Super Admin from environment settings
    # only when no Super Admin exists yet. No master/shared passwords are accepted.
    if (
        not user
        and clean_email == settings.DEFAULT_ADMIN_EMAIL.lower()
        and req.password == settings.DEFAULT_ADMIN_PASSWORD
        and not await db.users.find_one({"role": UserRole.SUPER_ADMIN.value})
    ):
        res = await db.users.insert_one({
            "email": clean_email,
            "hashed_password": hash_password(req.password),
            "full_name": settings.DEFAULT_ADMIN_NAME,
            "role": UserRole.SUPER_ADMIN.value,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        })
        user = await db.users.find_one({"_id": res.inserted_id})

    is_valid = bool(user) and verify_password(req.password, user.get("hashed_password", ""))

    if not user or not is_valid:
        record_failed_attempt(throttle_key)
        await audit_service.log_action(
            action="LOGIN_FAILED",
            entity_type="USER",
            user_email=clean_email,
            ip_address=client_ip,
            details={"reason": "Invalid credentials", "attempt": len(FAILED_ATTEMPTS.get(throttle_key, []))},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password credentials.",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been suspended. Please contact administrator.",
        )

    # Reset failed attempts upon successful authentication
    reset_failed_attempts(throttle_key)

    user_id = str(user["_id"])
    token_claims = {
        "sub": user_id,
        "email": user["email"],
        "role": user["role"],
        "name": user["full_name"],
        "entity_id": user.get("entity_id"),
    }

    access_token = create_access_token(token_claims)
    refresh_token = create_refresh_token(token_claims)

    # Audit log
    await audit_service.log_action(
        action="USER_LOGIN",
        entity_type="USER",
        user_id=user_id,
        user_email=user["email"],
        user_role=user["role"],
        ip_address=client_ip,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "avatar_url": user.get("avatar_url"),
            "entity_id": user.get("entity_id"),
        },
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(req: RefreshTokenRequest):
    payload = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Refresh token required.",
        )

    user_id = payload.get("sub")
    db = await get_db()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or not found.",
        )

    token_claims = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "name": user["full_name"],
        "entity_id": user.get("entity_id"),
    }

    access_token = create_access_token(token_claims)
    refresh_token = create_refresh_token(token_claims)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "avatar_url": user.get("avatar_url"),
            "entity_id": user.get("entity_id"),
        },
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    user = await db.users.find_one({"_id": ObjectId(current_user["id"])})
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "phone": user.get("phone"),
        "avatar_url": user.get("avatar_url"),
        "entity_id": user.get("entity_id"),
        "is_active": user.get("is_active", True),
        "created_at": user.get("created_at"),
    }


@router.post("/forgot-password")
async def forgot_password(req: PasswordResetRequest):
    db = await get_db()
    user = await db.users.find_one({"email": req.email.lower()})
    if user:
        reset_token = create_access_token(
            {"sub": str(user["_id"]), "type": "reset"},
            expires_delta=timedelta(hours=1),
        )
        await email_service.send_password_reset_email(user["email"], reset_token)

    return {"message": "If this email is registered, a password reset link has been dispatched."}


@router.post("/reset-password")
async def reset_password(req: PasswordResetConfirm):
    payload = decode_token(req.token)
    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Invalid token for password reset.")

    user_id = payload.get("sub")
    db = await get_db()
    new_hashed = hash_password(req.new_password)
    result = await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"hashed_password": new_hashed, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "Password updated successfully. You can now log in."}


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    user = await db.users.find_one({"_id": ObjectId(current_user["id"])})
    if not user or not verify_password(req.current_password, user.get("hashed_password", "")):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    new_hashed = hash_password(req.new_password)
    await db.users.update_one(
        {"_id": ObjectId(current_user["id"])},
        {"$set": {"hashed_password": new_hashed, "updated_at": datetime.now(timezone.utc)}},
    )

    return {"message": "Password changed successfully."}


@router.get("/check-email", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def check_email_availability(
    email: str = Query(..., description="Email address to verify"),
    type: Optional[str] = Query(None, description="FACULTY or STUDENT (informational)"),
    exclude_id: Optional[str] = Query(None, description="Student/faculty id being edited"),
):
    """Format, typo, domain (DNS) and duplicate check used by the admin forms while typing."""
    try:
        normalized = check_email_format(email)
    except EmailProblem as e:
        return {"available": False, "valid": False, "exists": False, "detail": e.message}
    db = await get_db()
    owner = await find_email_owner(db, normalized, exclude_id)
    if owner:
        return {
            "available": False,
            "valid": True,
            "exists": True,
            "detail": f"This email is already used by {owner}. Please use another email address.",
        }
    return {"available": True, "valid": True, "exists": False, "email": normalized, "detail": "Email address is valid and available."}
