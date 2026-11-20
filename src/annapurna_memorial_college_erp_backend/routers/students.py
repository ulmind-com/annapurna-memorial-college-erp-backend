from datetime import datetime, timezone
import logging
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    hash_password,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.student import (
    StudentCreate,
    StudentUpdate,
    StudentResponse,
    StudentStatus,
)
import secrets
import random
from annapurna_memorial_college_erp_backend.services.storage_service import storage_service
from annapurna_memorial_college_erp_backend.services.audit_service import audit_service
from annapurna_memorial_college_erp_backend.services.email_service import email_service

logger = logging.getLogger("erp.students")

router = APIRouter(prefix="/students", tags=["Students & Admissions"])


@router.get("")
async def list_students(
    course_code: Optional[str] = None,
    academic_session: Optional[str] = None,
    semester: Optional[int] = None,
    status: Optional[StudentStatus] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if course_code:
        query["course_code"] = course_code
    if academic_session:
        query["academic_session"] = academic_session
    if semester:
        query["semester"] = semester
    if status:
        query["status"] = status.value
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"roll_number": {"$regex": search, "$options": "i"}},
            {"registration_number": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]

    total = await db.students.count_documents(query)
    cursor = db.students.find(query).skip((page - 1) * limit).limit(limit).sort("roll_number", 1)
    items = []
    async for s in cursor:
        items.append({
            "id": str(s["_id"]),
            "roll_number": s["roll_number"],
            "registration_number": s.get("registration_number"),
            "full_name": s["full_name"],
            "email": s["email"],
            "phone": s["phone"],
            "course_code": s["course_code"],
            "course_name": s.get("course_name", s["course_code"]),
            "academic_session": s["academic_session"],
            "semester": s.get("semester", 1),
            "section": s.get("section", "A"),
            "date_of_birth": s.get("date_of_birth"),
            "gender": s.get("gender", "MALE"),
            "blood_group": s.get("blood_group"),
            "category": s.get("category", "GEN"),
            "guardian_name": s.get("guardian_name", ""),
            "guardian_phone": s.get("guardian_phone", ""),
            "guardian_relation": s.get("guardian_relation", "Father"),
            "address": s.get("address"),
            "status": s.get("status", "ACTIVE"),
            "avatar_url": s.get("avatar_url"),
            "documents": s.get("documents", []),
            "created_at": s.get("created_at"),
            "updated_at": s.get("updated_at"),
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
    }


@router.get("/{student_id}")
async def get_student(student_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    s = await db.students.find_one({"_id": ObjectId(student_id)})
    if not s:
        raise HTTPException(status_code=404, detail="Student record not found.")

    return {
        "id": str(s["_id"]),
        "roll_number": s["roll_number"],
        "registration_number": s.get("registration_number"),
        "full_name": s["full_name"],
        "email": s["email"],
        "phone": s["phone"],
        "course_code": s["course_code"],
        "course_name": s.get("course_name", s["course_code"]),
        "academic_session": s["academic_session"],
        "semester": s.get("semester", 1),
        "section": s.get("section", "A"),
        "date_of_birth": s.get("date_of_birth"),
        "gender": s.get("gender", "MALE"),
        "blood_group": s.get("blood_group"),
        "category": s.get("category", "GEN"),
        "guardian_name": s.get("guardian_name", ""),
        "guardian_phone": s.get("guardian_phone", ""),
        "guardian_relation": s.get("guardian_relation", "Father"),
        "address": s.get("address"),
        "status": s.get("status", "ACTIVE"),
        "avatar_url": s.get("avatar_url"),
        "documents": s.get("documents", []),
        "created_at": s.get("created_at"),
        "updated_at": s.get("updated_at"),
    }


@router.post("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_student(req: StudentCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    existing = await db.students.find_one({
        "$or": [{"roll_number": req.roll_number}, {"email": req.email.lower()}]
    })
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Student with this Roll Number or Email already exists.",
        )

    doc = req.model_dump()
    doc["email"] = doc["email"].lower()
    doc["status"] = doc["status"].value if hasattr(doc["status"], "value") else doc["status"]
    doc["gender"] = doc["gender"].value if hasattr(doc["gender"], "value") else doc["gender"]
    if not doc.get("avatar_url"):
        doc["avatar_url"] = f"https://api.dicebear.com/7.x/adventurer/svg?seed={req.roll_number}"
    doc["documents"] = []
    doc["created_at"] = datetime.now(timezone.utc)

    res = await db.students.insert_one(doc)
    student_id = str(res.inserted_id)

    # Automatically generate secure random password & create/update student portal login account
    user_exists = await db.users.find_one({"email": doc["email"]})
    generated_pwd = f"Amce#{secrets.token_hex(3)}!{random.randint(10, 99)}"
    if not user_exists:
        student_user = {
            "email": doc["email"],
            "hashed_password": hash_password(generated_pwd),
            "full_name": doc["full_name"],
            "role": UserRole.STUDENT.value,
            "phone": doc["phone"],
            "entity_id": student_id,
            "is_active": True,
            "avatar_url": doc["avatar_url"],
            "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(student_user)
    else:
        await db.users.update_one(
            {"_id": user_exists["_id"]},
            {
                "$set": {
                    "hashed_password": hash_password(generated_pwd),
                    "full_name": doc["full_name"],
                    "role": UserRole.STUDENT.value,
                    "entity_id": student_id,
                    "is_active": True,
                }
            },
        )

    # Always dispatch welcome email with credentials via Resend
    try:
        await email_service.send_onboarding_credentials_email(
            to_email=doc["email"],
            full_name=doc["full_name"],
            role="Teacher Trainee (Student)",
            temporary_password=generated_pwd,
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch student email: {e}")

    await audit_service.log_action(
        action="STUDENT_ENROLLED",
        entity_type="STUDENT",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=student_id,
        details={"roll_number": req.roll_number, "course": req.course_code},
    )

    return {"id": student_id, **doc, "generated_password": generated_pwd}


@router.post("/{student_id}/resend-credentials", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def resend_student_credentials(student_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    student = await db.students.find_one({"_id": ObjectId(student_id)})
    if not student:
        raise HTTPException(status_code=404, detail="Student record not found.")

    email = student["email"].lower()
    full_name = student["full_name"]
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
            "role": UserRole.STUDENT.value,
            "phone": student.get("phone", ""),
            "entity_id": student_id,
            "is_active": True,
            "avatar_url": student.get("avatar_url", ""),
            "created_at": datetime.now(timezone.utc),
        })

    await email_service.send_onboarding_credentials_email(
        to_email=email,
        full_name=full_name,
        role="Teacher Trainee (Student)",
        temporary_password=generated_pwd,
    )

    return {
        "message": f"Login credentials successfully dispatched to {email}",
        "email": email,
        "generated_password": generated_pwd,
    }


@router.put("/{student_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def update_student(
    student_id: str,
    req: StudentUpdate,
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
    if "gender" in update_data and hasattr(update_data["gender"], "value"):
        update_data["gender"] = update_data["gender"].value

    update_data["updated_at"] = datetime.now(timezone.utc)
    res = await db.students.update_one({"_id": ObjectId(student_id)}, {"$set": update_data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found.")

    await audit_service.log_action(
        action="STUDENT_UPDATED",
        entity_type="STUDENT",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=student_id,
        details=update_data,
    )

    return {"message": "Student updated successfully."}


@router.delete("/{student_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def delete_student(student_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    res = await db.students.delete_one({"_id": ObjectId(student_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Student not found.")

    await audit_service.log_action(
        action="STUDENT_DELETED",
        entity_type="STUDENT",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=student_id,
    )

    return {"message": "Student record deleted successfully."}


@router.post("/{student_id}/upload-document", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def upload_document(
    student_id: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    student = await db.students.find_one({"_id": ObjectId(student_id)})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    content = await file.read()
    file_url = await storage_service.upload_file(
        content,
        filename=f"{doc_type}_{file.filename}",
        folder="student_documents",
    )

    doc_entry = {
        "doc_type": doc_type,
        "filename": file.filename,
        "url": file_url,
        "uploaded_at": datetime.now(timezone.utc),
    }

    await db.students.update_one(
        {"_id": ObjectId(student_id)},
        {"$push": {"documents": doc_entry}},
    )

    return {"message": "Document uploaded successfully", "document": doc_entry}
