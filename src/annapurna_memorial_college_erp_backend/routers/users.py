from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    hash_password,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
)
from annapurna_memorial_college_erp_backend.services.audit_service import audit_service

router = APIRouter(prefix="/users", tags=["User & Access Management"])


@router.get("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def list_users(
    role: Optional[UserRole] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    db = await get_db()
    query = {}
    if role:
        query["role"] = role.value
    if is_active is not None:
        query["is_active"] = is_active
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]

    total = await db.users.count_documents(query)
    cursor = db.users.find(query).skip((page - 1) * limit).limit(limit).sort("created_at", -1)
    users = []
    async for u in cursor:
        users.append({
            "id": str(u["_id"]),
            "email": u["email"],
            "full_name": u["full_name"],
            "role": u["role"],
            "phone": u.get("phone"),
            "avatar_url": u.get("avatar_url"),
            "is_active": u.get("is_active", True),
            "entity_id": u.get("entity_id"),
            "created_at": u.get("created_at"),
            "updated_at": u.get("updated_at"),
        })

    return {
        "items": users,
        "total": total,
        "page": page,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
    }


@router.post("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_user(req: UserCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    existing = await db.users.find_one({"email": req.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists.")

    user_doc = {
        "email": req.email.lower(),
        "hashed_password": hash_password(req.password),
        "full_name": req.full_name,
        "role": req.role.value,
        "phone": req.phone,
        "is_active": req.is_active,
        "entity_id": req.entity_id,
        "avatar_url": f"https://api.dicebear.com/7.x/initials/svg?seed={req.full_name}",
        "created_at": datetime.now(timezone.utc),
    }

    res = await db.users.insert_one(user_doc)
    new_id = str(res.inserted_id)

    await audit_service.log_action(
        action="USER_CREATED",
        entity_type="USER",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=new_id,
        details={"created_email": req.email, "role": req.role.value},
    )

    user_doc.pop("_id", None)
    return {
        "id": new_id,
        **user_doc,
        "hashed_password": None,
    }


@router.put("/{user_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def update_user(
    user_id: str,
    req: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update.")

    update_data["updated_at"] = datetime.now(timezone.utc)
    res = await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")

    await audit_service.log_action(
        action="USER_UPDATED",
        entity_type="USER",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=user_id,
        details=update_data,
    )

    return {"message": "User updated successfully"}


@router.delete("/{user_id}", dependencies=[Depends(require_roles([UserRole.SUPER_ADMIN]))])
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")

    db = await get_db()
    res = await db.users.delete_one({"_id": ObjectId(user_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")

    await audit_service.log_action(
        action="USER_DELETED",
        entity_type="USER",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=user_id,
    )

    return {"message": "User deleted successfully."}
