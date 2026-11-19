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
from annapurna_memorial_college_erp_backend.schemas.attendance import (
    AttendanceRecordCreate,
    AttendanceRecordResponse,
    StudentAttendanceSummary,
)
from annapurna_memorial_college_erp_backend.services.audit_service import audit_service

router = APIRouter(prefix="/attendance", tags=["Attendance Management"])


@router.post("", dependencies=[Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def record_attendance(
    req: AttendanceRecordCreate,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    total = len(req.records)
    p_count = sum(1 for r in req.records if r.status.value == "PRESENT")
    a_count = sum(1 for r in req.records if r.status.value == "ABSENT")
    percentage = (p_count / total * 100.0) if total > 0 else 0.0

    doc = req.model_dump()
    doc["faculty_id"] = current_user["id"]
    doc["faculty_name"] = current_user.get("name", "Faculty")
    doc["total_students"] = total
    doc["present_count"] = p_count
    doc["absent_count"] = a_count
    doc["percentage"] = round(percentage, 2)
    doc["created_at"] = datetime.now(timezone.utc)

    # Upsert attendance record for that date & subject
    filter_q = {
        "date": req.date,
        "course_code": req.course_code,
        "semester": req.semester,
        "subject_code": req.subject_code,
        "section": req.section,
    }
    await db.attendance.update_one(filter_q, {"$set": doc}, upsert=True)

    await audit_service.log_action(
        action="ATTENDANCE_RECORDED",
        entity_type="ATTENDANCE",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        details={
            "date": req.date,
            "subject": req.subject_code,
            "course": req.course_code,
            "present": p_count,
            "total": total,
        },
    )

    return {"message": "Attendance recorded successfully", "present": p_count, "total": total}


@router.get("/sheet")
async def get_attendance_sheet(
    date: str,
    course_code: str,
    semester: int,
    subject_code: str,
    section: str = "A",
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    rec = await db.attendance.find_one({
        "date": date,
        "course_code": course_code,
        "semester": semester,
        "subject_code": subject_code,
        "section": section,
    })
    if not rec:
        return {"records": [], "recorded": False}

    return {
        "id": str(rec["_id"]),
        "date": rec["date"],
        "course_code": rec["course_code"],
        "semester": rec["semester"],
        "subject_code": rec["subject_code"],
        "section": rec["section"],
        "faculty_name": rec.get("faculty_name"),
        "records": rec.get("records", []),
        "present_count": rec.get("present_count", 0),
        "total_students": rec.get("total_students", 0),
        "recorded": True,
    }


@router.get("/analytics")
async def get_attendance_analytics(
    course_code: str,
    semester: int,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    # Find all attendance sessions for this course and semester
    cursor = db.attendance.find({"course_code": course_code, "semester": semester})
    sessions = await cursor.to_list(length=1000)

    student_stats = {}
    for session in sessions:
        for r in session.get("records", []):
            sid = r["student_id"]
            if sid not in student_stats:
                student_stats[sid] = {
                    "student_id": sid,
                    "roll_number": r["roll_number"],
                    "student_name": r["student_name"],
                    "total_classes": 0,
                    "attended": 0,
                }
            student_stats[sid]["total_classes"] += 1
            if r["status"] in ["PRESENT", "LATE"]:
                student_stats[sid]["attended"] += 1

    result = []
    for sid, s in student_stats.items():
        pct = (s["attended"] / s["total_classes"] * 100.0) if s["total_classes"] > 0 else 100.0
        result.append({
            "student_id": sid,
            "roll_number": s["roll_number"],
            "student_name": s["student_name"],
            "course_code": course_code,
            "semester": semester,
            "total_classes": s["total_classes"],
            "classes_attended": s["attended"],
            "percentage": round(pct, 2),
            "is_short_attendance": pct < 75.0,  # Below 75% BSAEU threshold
        })

    result.sort(key=lambda x: x["roll_number"])
    return result
