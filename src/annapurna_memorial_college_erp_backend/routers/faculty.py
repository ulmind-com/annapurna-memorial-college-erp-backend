from datetime import datetime, timezone
import logging
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    hash_password,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.faculty import (
    FacultyCreate,
    FacultyUpdate,
    FacultyResponse,
    FacultyStatus,
)
import secrets
import random
from annapurna_memorial_college_erp_backend.services.email_service import email_service
from annapurna_memorial_college_erp_backend.services.audit_service import audit_service

logger = logging.getLogger("erp.faculty")

router = APIRouter(prefix="/faculty", tags=["Faculty & Staff"])


@router.get("")
async def list_faculty(
    department: Optional[str] = None,
    status: Optional[FacultyStatus] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if department:
        query["department"] = department
    if status:
        query["status"] = status.value
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"employee_id": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"department": {"$regex": search, "$options": "i"}},
        ]

    total = await db.faculty.count_documents(query)
    cursor = db.faculty.find(query).skip((page - 1) * limit).limit(limit).sort("full_name", 1)
    items = []
    async for f in cursor:
        items.append({
            "id": str(f["_id"]),
            "employee_id": f["employee_id"],
            "full_name": f["full_name"],
            "email": f["email"],
            "phone": f["phone"],
            "department": f["department"],
            "designation": f["designation"],
            "qualification": f["qualification"],
            "specialization": f.get("specialization"),
            "joining_date": f.get("joining_date"),
            "assigned_subjects": f.get("assigned_subjects", []),
            "status": f.get("status", "ACTIVE"),
            "avatar_url": f.get("avatar_url"),
            "created_at": f.get("created_at"),
            "updated_at": f.get("updated_at"),
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
    }


@router.get("/{faculty_id}")
async def get_faculty(faculty_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    f = await db.faculty.find_one({"_id": ObjectId(faculty_id)})
    if not f:
        raise HTTPException(status_code=404, detail="Faculty member not found.")

    return {
        "id": str(f["_id"]),
        "employee_id": f["employee_id"],
        "full_name": f["full_name"],
        "email": f["email"],
        "phone": f["phone"],
        "department": f["department"],
        "designation": f["designation"],
        "qualification": f["qualification"],
        "specialization": f.get("specialization"),
        "joining_date": f.get("joining_date"),
        "assigned_subjects": f.get("assigned_subjects", []),
        "status": f.get("status", "ACTIVE"),
        "avatar_url": f.get("avatar_url"),
        "created_at": f.get("created_at"),
        "updated_at": f.get("updated_at"),
    }


@router.post("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_faculty(req: FacultyCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    clean_email = req.email.strip().lower()
    clean_emp_id = req.employee_id.strip()

    # 1. Check if email is already registered to another faculty member
    existing_fac_email = await db.faculty.find_one({"email": clean_email})
    if existing_fac_email:
        raise HTTPException(
            status_code=400,
            detail=f"This email '{req.email}' is already registered to faculty member '{existing_fac_email.get('full_name')}'. Please provide another email address."
        )

    # 2. Check if employee ID is already in use
    existing_fac_emp = await db.faculty.find_one({"employee_id": clean_emp_id})
    if existing_fac_emp:
        raise HTTPException(
            status_code=400,
            detail=f"Employee ID '{req.employee_id}' is already assigned to faculty member '{existing_fac_emp.get('full_name')}'. Please enter a unique Employee ID."
        )

    # 3. Check if email is already registered in users collection
    existing_user = await db.users.find_one({"email": clean_email})
    if existing_user:
        role_label = existing_user.get("role", "user")
        raise HTTPException(
            status_code=400,
            detail=f"This email '{req.email}' is already in use by an existing {role_label} account. Please provide another email address."
        )

    doc = req.model_dump()
    doc["email"] = doc["email"].lower()
    doc["status"] = doc["status"].value if hasattr(doc["status"], "value") else doc["status"]
    if not doc.get("avatar_url"):
        doc["avatar_url"] = f"https://api.dicebear.com/7.x/micah/svg?seed={req.employee_id}"
    doc["created_at"] = datetime.now(timezone.utc)

    res = await db.faculty.insert_one(doc)
    faculty_id = str(res.inserted_id)

    # Automatically generate secure random password & create/update user login
    user_exists = await db.users.find_one({"email": doc["email"]})
    generated_pwd = f"Amce#{secrets.token_hex(3)}!{random.randint(10, 99)}"
    if not user_exists:
        faculty_user = {
            "email": doc["email"],
            "hashed_password": hash_password(generated_pwd),
            "full_name": doc["full_name"],
            "role": UserRole.FACULTY.value,
            "phone": doc["phone"],
            "entity_id": faculty_id,
            "is_active": True,
            "avatar_url": doc["avatar_url"],
            "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(faculty_user)
    else:
        await db.users.update_one(
            {"_id": user_exists["_id"]},
            {
                "$set": {
                    "hashed_password": hash_password(generated_pwd),
                    "full_name": doc["full_name"],
                    "role": UserRole.FACULTY.value,
                    "entity_id": faculty_id,
                    "is_active": True,
                }
            },
        )

    # Always dispatch welcome email with credentials via Resend
    try:
        await email_service.send_onboarding_credentials_email(
            to_email=doc["email"],
            full_name=doc["full_name"],
            role="Faculty / Assistant Professor",
            temporary_password=generated_pwd,
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch faculty email: {e}")

    await audit_service.log_action(
        action="FACULTY_ONBOARDED",
        entity_type="FACULTY",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=faculty_id,
        details={"employee_id": req.employee_id, "department": req.department},
    )

    doc.pop("_id", None)
    return {"id": faculty_id, **doc, "generated_password": generated_pwd}


@router.post("/{faculty_id}/resend-credentials", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def resend_faculty_credentials(faculty_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    faculty_rec = await db.faculty.find_one({"_id": ObjectId(faculty_id)})
    if not faculty_rec:
        raise HTTPException(status_code=404, detail="Faculty record not found.")

    email = faculty_rec["email"].lower()
    full_name = faculty_rec["full_name"]
    generated_pwd = f"Amce#{secrets.token_hex(3)}!{random.randint(10, 99)}"

    user_exists = await db.users.find_one({"email": email})
    if user_exists:
        await db.users.update_one(
            {"_id": user_exists["_id"]},
            {
                "$set": {
                    "hashed_password": hash_password(generated_pwd),
                    "is_active": True,
                }
            },
        )
    else:
        await db.users.insert_one({
            "email": email,
            "hashed_password": hash_password(generated_pwd),
            "full_name": full_name,
            "role": UserRole.FACULTY.value,
            "phone": faculty_rec.get("phone", ""),
            "entity_id": faculty_id,
            "is_active": True,
            "avatar_url": faculty_rec.get("avatar_url", ""),
            "created_at": datetime.now(timezone.utc),
        })

    await email_service.send_onboarding_credentials_email(
        to_email=email,
        full_name=full_name,
        role="Faculty / Assistant Professor",
        temporary_password=generated_pwd,
    )

    return {
        "message": f"Login credentials successfully dispatched to {email}",
        "email": email,
        "generated_password": generated_pwd,
    }


@router.put("/{faculty_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def update_faculty(
    faculty_id: str,
    req: FacultyUpdate,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update.")

    if "email" in update_data:
        update_data["email"] = update_data["email"].lower()
    if "status" in update_data and hasattr(update_data["status"], "value"):
        update_data["status"] = update_data["status"].value

    update_data["updated_at"] = datetime.now(timezone.utc)
    res = await db.faculty.update_one({"_id": ObjectId(faculty_id)}, {"$set": update_data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Faculty member not found.")

    # Synchronize user account if full_name, email, or avatar_url changed
    user_sync = {}
    if "full_name" in update_data:
        user_sync["full_name"] = update_data["full_name"]
    if "email" in update_data:
        user_sync["email"] = update_data["email"]
    if "avatar_url" in update_data:
        user_sync["avatar_url"] = update_data["avatar_url"]
    if user_sync:
        await db.users.update_many({"entity_id": faculty_id}, {"$set": user_sync})

    await audit_service.log_action(
        action="FACULTY_UPDATED",
        entity_type="FACULTY",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=faculty_id,
        details=update_data,
    )

    return {"message": "Faculty updated successfully."}


@router.delete("/{faculty_id}", dependencies=[Depends(require_roles([UserRole.SUPER_ADMIN]))])
async def delete_faculty(faculty_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    res = await db.faculty.delete_one({"_id": ObjectId(faculty_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Faculty member not found.")

    await audit_service.log_action(
        action="FACULTY_DELETED",
        entity_type="FACULTY",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=faculty_id,
    )

    return {"message": "Faculty member deleted successfully."}
