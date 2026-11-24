from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.academic import (
    CourseCreate,
    CourseUpdate,
    CourseResponse,
    SubjectCreate,
    SubjectUpdate,
    SubjectResponse,
    AcademicSessionCreate,
    AcademicSessionResponse,
    TimetableSlotCreate,
)

router = APIRouter(prefix="/academics", tags=["Academic Curriculum"])


# COURSES
@router.get("/courses")
async def list_courses(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    cursor = db.courses.find().sort("name", 1)
    courses = []
    async for c in cursor:
        courses.append({
            "id": str(c["_id"]),
            "code": c["code"],
            "name": c["name"],
            "department": c.get("department", "Education"),
            "duration_years": c.get("duration_years", 2),
            "total_semesters": c.get("total_semesters", 4),
            "affiliation": c.get("affiliation", "BSAEU & NCTE"),
            "max_intake": c.get("max_intake", 100),
            "description": c.get("description"),
            "is_active": c.get("is_active", True),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
        })
    return courses


@router.post("/courses", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_course(req: CourseCreate):
    db = await get_db()
    existing = await db.courses.find_one({"code": req.code.upper()})
    if existing:
        raise HTTPException(status_code=400, detail="Course code already exists.")

    doc = req.model_dump()
    doc["code"] = doc["code"].upper()
    doc["created_at"] = datetime.now(timezone.utc)
    res = await db.courses.insert_one(doc)
    doc.pop("_id", None)
    return {"id": str(res.inserted_id), **doc}


@router.put("/courses/{course_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def update_course(course_id: str, req: CourseUpdate):
    db = await get_db()
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc)
    res = await db.courses.update_one({"_id": ObjectId(course_id)}, {"$set": update_data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found.")
    return {"message": "Course updated successfully."}


# SUBJECTS
@router.get("/subjects")
async def list_subjects(
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if course_code:
        query["course_code"] = course_code.upper()
    if semester:
        query["semester"] = semester

    cursor = db.subjects.find(query).sort([("semester", 1), ("code", 1)])
    subjects = []
    async for s in cursor:
        subjects.append({
            "id": str(s["_id"]),
            "code": s["code"],
            "title": s["title"],
            "course_code": s["course_code"],
            "semester": s["semester"],
            "credits": s.get("credits", 4),
            "full_marks": s.get("full_marks", 100),
            "pass_marks": s.get("pass_marks", 40),
            "theory_marks": s.get("theory_marks", 70),
            "practical_marks": s.get("practical_marks", 30),
            "faculty_id": s.get("faculty_id"),
            "faculty_name": s.get("faculty_name"),
            "is_elective": s.get("is_elective", False),
            "created_at": s.get("created_at"),
            "updated_at": s.get("updated_at"),
        })
    return subjects


@router.post("/subjects", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_subject(req: SubjectCreate):
    db = await get_db()
    existing = await db.subjects.find_one({"code": req.code.upper()})
    if existing:
        raise HTTPException(status_code=400, detail="Subject code already exists.")

    doc = req.model_dump()
    doc["code"] = doc["code"].upper()
    doc["course_code"] = doc["course_code"].upper()

    if doc.get("faculty_id"):
        fac = await db.faculty.find_one({"_id": ObjectId(doc["faculty_id"])})
        if fac:
            doc["faculty_name"] = fac["full_name"]

    doc["created_at"] = datetime.now(timezone.utc)
    res = await db.subjects.insert_one(doc)
    doc.pop("_id", None)
    return {"id": str(res.inserted_id), **doc}


@router.put("/subjects/{subject_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def update_subject(subject_id: str, req: SubjectUpdate):
    db = await get_db()
    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if "faculty_id" in update_data and update_data["faculty_id"]:
        fac = await db.faculty.find_one({"_id": ObjectId(update_data["faculty_id"])})
        if fac:
            update_data["faculty_name"] = fac["full_name"]

    update_data["updated_at"] = datetime.now(timezone.utc)
    res = await db.subjects.update_one({"_id": ObjectId(subject_id)}, {"$set": update_data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Subject not found.")
    return {"message": "Subject updated successfully."}


# SESSIONS
@router.get("/sessions")
async def list_sessions(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    cursor = db.academic_sessions.find().sort("start_year", -1)
    sessions = []
    async for s in cursor:
        sessions.append({
            "id": str(s["_id"]),
            "label": s["label"],
            "start_year": s["start_year"],
            "end_year": s["end_year"],
            "is_current": s.get("is_current", False),
        })
    return sessions


@router.post("/sessions", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_session(req: AcademicSessionCreate):
    db = await get_db()
    if req.is_current:
        await db.academic_sessions.update_many({}, {"$set": {"is_current": False}})

    doc = req.model_dump()
    res = await db.academic_sessions.insert_one(doc)
    doc.pop("_id", None)
    return {"id": str(res.inserted_id), **doc}


# TIMETABLE
@router.get("/timetable")
async def list_timetable(
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    day: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}

    # If student, match their enrolled course/semester if not specified
    if current_user.get("role") == UserRole.STUDENT and not course_code:
        st = await db.students.find_one({
            "$or": [
                {"email": current_user.get("email")},
                {"_id": ObjectId(current_user["id"]) if ObjectId.is_valid(current_user.get("id", "")) else None},
            ]
        })
        if st:
            course_code = st.get("course_code") or st.get("course")
            if not semester:
                semester = st.get("semester", 1)

    if course_code:
        query["course_code"] = course_code.upper()
    if semester:
        query["semester"] = int(semester)
    if day:
        query["day"] = day.upper()

    cursor = db.timetable_slots.find(query).sort("time", 1)
    slots = []
    async for s in cursor:
        slots.append({
            "id": str(s["_id"]),
            "day": s["day"],
            "course_code": s["course_code"],
            "semester": s["semester"],
            "time": s["time"],
            "subject": s["subject"],
            "class_label": s.get("class_label") or f"{s['course_code']} Sem {s['semester']}",
            "room": s.get("room", "Room 101"),
            "faculty": s.get("faculty", "Faculty Member"),
            "type": s.get("type", "Theory Lecture"),
            "status": s.get("status", "Scheduled"),
            "created_at": s.get("created_at"),
        })
    return slots


@router.post("/timetable", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def create_timetable_slot(req: TimetableSlotCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    doc = req.model_dump()
    doc["day"] = doc["day"].upper()
    doc["course_code"] = doc["course_code"].upper()
    doc["created_at"] = datetime.now(timezone.utc)
    doc["created_by"] = current_user.get("id")

    res = await db.timetable_slots.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return doc


@router.delete("/timetable/{slot_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def delete_timetable_slot(slot_id: str):
    db = await get_db()
    try:
        query = {"_id": ObjectId(slot_id)}
    except Exception:
        query = {"id": slot_id}

    res = await db.timetable_slots.delete_one(query)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Timetable slot not found.")
    return {"message": "Timetable slot deleted successfully."}

