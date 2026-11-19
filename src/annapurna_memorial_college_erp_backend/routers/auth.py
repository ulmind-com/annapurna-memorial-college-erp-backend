from datetime import datetime, timezone, timedelta
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Request
from annapurna_memorial_college_erp_backend.config import settings
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
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

router = APIRouter(prefix="/auth", tags=["Authentication & Security"])


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    db = await get_db()
    user = await db.users.find_one({"email": req.email.lower()})

    # If no user found and matching default admin, auto-bootstrap default admin
    if not user and req.email.lower() == settings.DEFAULT_ADMIN_EMAIL.lower():
        admin_doc = {
            "email": settings.DEFAULT_ADMIN_EMAIL.lower(),
            "hashed_password": hash_password(settings.DEFAULT_ADMIN_PASSWORD),
            "full_name": settings.DEFAULT_ADMIN_NAME,
            "role": UserRole.SUPER_ADMIN.value,
            "phone": "+91 9876543210",
            "is_active": True,
            "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150",
            "created_at": datetime.now(timezone.utc),
        }
        res = await db.users.insert_one(admin_doc)
        user = await db.users.find_one({"_id": res.inserted_id})

    if not user or not verify_password(req.password, user.get("hashed_password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password credentials.",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been suspended. Please contact administrator.",
        )

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
        ip_address=request.client.host if request.client else None,
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
