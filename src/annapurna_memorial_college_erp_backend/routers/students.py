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

from annapurna_memorial_college_erp_backend.validators import validate_new_email
from annapurna_memorial_college_erp_backend.deps import (
    get_student_record, get_faculty_scope, classes_query, serialize_student, is_student, is_faculty, oid,
)

router = APIRouter(prefix="/students", tags=["Students & Admissions"])


@router.get("")
async def list_students(
    course_code: Optional[str] = None,
    academic_session: Optional[str] = None,
    semester: Optional[int] = None,
    status: Optional[StudentStatus] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if is_student(current_user):
        raise HTTPException(status_code=403, detail="Students can only view their own profile (/students/me).")
    if is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        query.update(classes_query(scope["classes"]))
    if course_code:
        query["course_code"] = course_code.upper()
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


@router.get("/me")
async def get_my_student_profile(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    rec = await get_student_record(db, current_user, required=True)
    return serialize_student(rec)


@router.get("/{student_id}")
async def get_student(student_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    s = await db.students.find_one({"_id": oid(student_id)})
    if s and is_student(current_user) and str(s["_id"]) != current_user.get("entity_id"):
        raise HTTPException(status_code=403, detail="Access denied.")
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
    clean_email = req.email.strip().lower()
    clean_roll = req.roll_number.strip()

    # Valid, non-typo, deliverable email not used by any student/faculty/login
    clean_email = await validate_new_email(db, clean_email)
    existing_st_roll = await db.students.find_one({"roll_number": clean_roll})
    if existing_st_roll:
        raise HTTPException(
            status_code=400,
            detail=f"Roll Number '{req.roll_number}' already belongs to student '{existing_st_roll.get('full_name')}'. Please enter a unique Roll Number."
        )

    # Course must exist and have a vacant seat
    course_exists = await db.courses.find_one({"code": req.course_code.strip().upper()})
    if not course_exists:
        raise HTTPException(status_code=400, detail=f"Course '{req.course_code}' does not exist. Create it in Academic Structure first.")
    if req.semester < 1 or req.semester > course_exists.get("total_semesters", 8):
        raise HTTPException(status_code=400, detail=f"Semester must be between 1 and {course_exists.get('total_semesters', 8)}.")
    enrolled = await db.students.count_documents({"course_code": course_exists["code"]})
    if course_exists.get("max_intake") and enrolled >= course_exists["max_intake"]:
        raise HTTPException(status_code=400, detail=f"No seats left in {course_exists['code']} ({enrolled}/{course_exists['max_intake']} enrolled).")
    if req.registration_number and await db.students.find_one({"registration_number": req.registration_number.strip()}):
        raise HTTPException(status_code=400, detail="This registration number is already assigned to another student.")

    doc = req.model_dump()
    doc["email"] = clean_email
    doc["roll_number"] = clean_roll
    doc["status"] = doc["status"].value if hasattr(doc["status"], "value") else doc["status"]
    doc["gender"] = doc["gender"].value if hasattr(doc["gender"], "value") else doc["gender"]

    # Dynamically resolve course_name from db.courses
    clean_code = req.course_code.strip()
    norm_code = clean_code.replace(".", "").upper()
    matched_course = await db.courses.find_one({
        "$or": [
            {"code": {"$regex": f"^{clean_code}$", "$options": "i"}},
            {"code": {"$regex": f"^{norm_code}$", "$options": "i"}},
        ]
    })
    if matched_course:
        doc["course_code"] = matched_course.get("code", clean_code)
        doc["course_name"] = matched_course.get("name", doc.get("course_name") or clean_code)
    elif not doc.get("course_name"):
        doc["course_name"] = clean_code

    if not doc.get("registration_number"):
        doc.pop("registration_number", None)
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
            role="Student",
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

    doc.pop("_id", None)
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
        role="Student",
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
        update_data["email"] = await validate_new_email(db, update_data["email"], exclude_entity_id=student_id)
    if "roll_number" in update_data:
        update_data["roll_number"] = update_data["roll_number"].strip()
        dup = await db.students.find_one({"roll_number": update_data["roll_number"], "_id": {"$ne": oid(student_id)}})
        if dup:
            raise HTTPException(status_code=400, detail=f"Roll number already belongs to '{dup.get('full_name')}'.")
    if update_data.get("registration_number"):
        update_data["registration_number"] = update_data["registration_number"].strip()
        dup = await db.students.find_one({"registration_number": update_data["registration_number"], "_id": {"$ne": oid(student_id)}})
        if dup:
            raise HTTPException(status_code=400, detail=f"Registration number already belongs to '{dup.get('full_name')}'.")
    if "status" in update_data and hasattr(update_data["status"], "value"):
        update_data["status"] = update_data["status"].value
    if "gender" in update_data and hasattr(update_data["gender"], "value"):
        update_data["gender"] = update_data["gender"].value

    if update_data.get("course_code"):
        clean_code = update_data["course_code"].strip()
        norm_code = clean_code.replace(".", "").upper()
        matched_course = await db.courses.find_one({
            "$or": [
                {"code": {"$regex": f"^{clean_code}$", "$options": "i"}},
                {"code": {"$regex": f"^{norm_code}$", "$options": "i"}},
            ]
        })
        if matched_course:
            update_data["course_code"] = matched_course.get("code", clean_code)
            update_data["course_name"] = matched_course.get("name")

    update_data["updated_at"] = datetime.now(timezone.utc)
    res = await db.students.update_one({"_id": oid(student_id)}, {"$set": update_data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found.")

    # Synchronize user account if full_name, email, or avatar_url changed
    user_sync = {}
    if "full_name" in update_data:
        user_sync["full_name"] = update_data["full_name"]
    if "email" in update_data:
        user_sync["email"] = update_data["email"]
    if "avatar_url" in update_data:
        user_sync["avatar_url"] = update_data["avatar_url"]
    if user_sync:
        await db.users.update_many({"entity_id": student_id}, {"$set": user_sync})

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
    res = await db.students.delete_one({"_id": oid(student_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Student not found.")
    await db.users.delete_many({"entity_id": student_id})

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
