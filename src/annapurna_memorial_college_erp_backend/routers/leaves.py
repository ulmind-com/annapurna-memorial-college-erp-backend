from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from annapurna_memorial_college_erp_backend.database import DatabaseManager
from annapurna_memorial_college_erp_backend.security import get_current_user, require_roles, UserRole
from annapurna_memorial_college_erp_backend.deps import (
    get_student_record, get_faculty_scope, classes_query, is_student, is_faculty, oid,
)
from annapurna_memorial_college_erp_backend.services.notification_service import notification_service

router = APIRouter(prefix="/leaves", tags=["Leave Applications"])


class LeaveCreate(BaseModel):
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    roll_number: Optional[str] = None
    course_code: Optional[str] = None
    semester: Optional[int] = None
    leave_type: str = "MEDICAL"  # MEDICAL, PERSONAL, ACADEMIC, EMERGENCY
    start_date: str
    end_date: str
    total_days: int = 1
    reason: str


class LeaveReview(BaseModel):
    status: str  # APPROVED, REJECTED
    remarks: str = ""
    reviewer_name: Optional[str] = None


class LeaveResponse(BaseModel):
    id: str
    student_id: str
    student_name: str
    roll_number: str
    course_code: str
    semester: int
    leave_type: str
    start_date: str
    end_date: str
    total_days: int
    reason: str
    status: str
    applied_at: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    remarks: Optional[str] = None


def _out(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    return doc


@router.get("", response_model=List[LeaveResponse])
async def get_leaves(
    student_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    db = DatabaseManager.get_database()
    query: dict = {}
    if is_student(current_user):
        st = await get_student_record(db, current_user, required=True)
        query["student_id"] = str(st["_id"])
    elif is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        query.update(classes_query(scope["classes"]))
        if student_id:
            query["student_id"] = student_id
    elif student_id:
        query["$or"] = [{"student_id": student_id}, {"roll_number": student_id}]
    if status and status != "ALL":
        query["status"] = status

    cursor = db.leaves.find(query).sort("applied_at", -1).skip((page - 1) * limit).limit(limit)
    return [_out(doc) async for doc in cursor]


@router.post("", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
async def apply_leave(data: LeaveCreate, current_user: dict = Depends(get_current_user)):
    db = DatabaseManager.get_database()
    if not is_student(current_user):
        raise HTTPException(status_code=403, detail="Only students can apply for leave.")
    st = await get_student_record(db, current_user, required=True)
    try:
        start = datetime.fromisoformat(data.start_date[:10])
        end = datetime.fromisoformat(data.end_date[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid leave dates.")
    if end < start:
        raise HTTPException(status_code=400, detail="End date cannot be before start date.")
    if not data.reason.strip():
        raise HTTPException(status_code=400, detail="Reason is required.")

    doc = {
        "student_id": str(st["_id"]),
        "student_name": st.get("full_name", ""),
        "roll_number": st.get("roll_number", ""),
        "course_code": st.get("course_code", ""),
        "semester": st.get("semester", 1),
        "leave_type": data.leave_type,
        "start_date": data.start_date[:10],
        "end_date": data.end_date[:10],
        "total_days": (end - start).days + 1,
        "reason": data.reason.strip(),
        "status": "PENDING",
        "applied_at": datetime.utcnow().isoformat(),
        "reviewed_by": None,
        "reviewed_at": None,
        "remarks": None,
    }
    await db.leaves.insert_one(doc)
    return _out(doc)


@router.post("/{leave_id}/review", response_model=LeaveResponse)
async def review_leave(
    leave_id: str,
    data: LeaveReview,
    current_user: dict = Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN])),
):
    db = DatabaseManager.get_database()
    if data.status not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail="Status must be APPROVED or REJECTED.")
    leave = await db.leaves.find_one({"_id": oid(leave_id)})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave application not found")
    if is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        if (leave.get("course_code"), leave.get("semester")) not in scope["classes"]:
            raise HTTPException(status_code=403, detail="This student is not in your assigned classes.")

    res = await db.leaves.find_one_and_update(
        {"_id": leave["_id"]},
        {"$set": {
            "status": data.status,
            "remarks": data.remarks,
            "reviewed_by": current_user.get("full_name") or data.reviewer_name,
            "reviewed_at": datetime.utcnow().isoformat(),
        }},
        return_document=True,
    )
    user_ids = [str(u["_id"]) async for u in db.users.find({"entity_id": leave.get("student_id")}, {"_id": 1})]
    await notification_service.notify_users(
        db, user_ids, f"Leave {data.status.title()}",
        f"Your leave from {leave.get('start_date')} to {leave.get('end_date')} was {data.status.lower()}.",
        {"type": "LEAVE", "id": leave_id},
    )
    return _out(res)
