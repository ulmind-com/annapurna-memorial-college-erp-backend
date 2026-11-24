"""Shared helpers that map an authenticated user to their student / faculty record
and compute the data scope each role is allowed to see."""
from typing import Optional, List, Dict, Any
from bson import ObjectId
from fastapi import HTTPException

from annapurna_memorial_college_erp_backend.security import UserRole

ADMIN_ROLES = {UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value}


def oid(value: str) -> ObjectId:
    """Parse an ObjectId or raise a clean 404."""
    if not value or not ObjectId.is_valid(value):
        raise HTTPException(status_code=404, detail="Record not found.")
    return ObjectId(value)


def is_admin(user: dict) -> bool:
    return user.get("role") in ADMIN_ROLES


def is_faculty(user: dict) -> bool:
    return user.get("role") in (UserRole.FACULTY.value, "TEACHER")


def is_student(user: dict) -> bool:
    return user.get("role") == UserRole.STUDENT.value


async def _find_by_entity_or_email(collection, user: dict) -> Optional[dict]:
    entity_id = user.get("entity_id")
    if entity_id and ObjectId.is_valid(entity_id):
        rec = await collection.find_one({"_id": ObjectId(entity_id)})
        if rec:
            return rec
    email = (user.get("email") or "").lower()
    if email:
        return await collection.find_one({"email": email})
    return None


async def get_student_record(db, user: dict, required: bool = False) -> Optional[dict]:
    rec = await _find_by_entity_or_email(db.students, user)
    if not rec and required:
        raise HTTPException(
            status_code=404,
            detail="No student profile is linked to this account. Please contact the college office.",
        )
    return rec


async def get_faculty_record(db, user: dict, required: bool = False) -> Optional[dict]:
    rec = await _find_by_entity_or_email(db.faculty, user)
    if not rec and required:
        raise HTTPException(
            status_code=404,
            detail="No faculty profile is linked to this account. Please contact the college office.",
        )
    return rec


async def get_faculty_subjects(db, faculty: Optional[dict]) -> List[dict]:
    """Subjects taught by a faculty member: subjects.faculty_id OR faculty.assigned_subjects."""
    if not faculty:
        return []
    fac_id = str(faculty["_id"])
    codes = [c.upper() for c in (faculty.get("assigned_subjects") or []) if c]
    query: Dict[str, Any] = {"$or": [{"faculty_id": fac_id}]}
    if codes:
        query["$or"].append({"code": {"$in": codes}})
    return [s async for s in db.subjects.find(query)]


async def get_faculty_scope(db, user: dict) -> Dict[str, Any]:
    """Return {'faculty': rec, 'subjects': [...], 'classes': [(course_code, semester), ...]}"""
    faculty = await get_faculty_record(db, user)
    subjects = await get_faculty_subjects(db, faculty)
    classes = sorted({(s["course_code"].upper(), int(s.get("semester", 1))) for s in subjects})
    return {"faculty": faculty, "subjects": subjects, "classes": classes}


def classes_query(classes: List[tuple]) -> Dict[str, Any]:
    """Mongo filter matching any (course_code, semester) pair. Matches nothing if empty."""
    if not classes:
        return {"_id": {"$exists": False}}
    return {"$or": [{"course_code": c, "semester": s} for c, s in classes]}


def serialize_student(s: dict) -> dict:
    return {
        "id": str(s["_id"]),
        "roll_number": s.get("roll_number", ""),
        "registration_number": s.get("registration_number"),
        "full_name": s.get("full_name", ""),
        "email": s.get("email", ""),
        "phone": s.get("phone", ""),
        "course_code": s.get("course_code", ""),
        "course_name": s.get("course_name", s.get("course_code", "")),
        "academic_session": s.get("academic_session", ""),
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


async def student_user_ids(db, student_query: Dict[str, Any]) -> List[str]:
    """User ids (as strings) of student accounts whose student record matches the query."""
    ids = [str(s["_id"]) async for s in db.students.find(student_query, {"_id": 1})]
    if not ids:
        return []
    return [str(u["_id"]) async for u in db.users.find({"entity_id": {"$in": ids}}, {"_id": 1})]
