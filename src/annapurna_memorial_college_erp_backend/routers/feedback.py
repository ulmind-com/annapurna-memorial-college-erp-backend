from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from annapurna_memorial_college_erp_backend.database import DatabaseManager
from annapurna_memorial_college_erp_backend.deps import (
    get_student_record, get_faculty_record, get_faculty_subjects, is_student, is_faculty, oid,
)
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    UserRole,
)

router = APIRouter(prefix="/feedback", tags=["Student Feedback"])


class FeedbackCreate(BaseModel):
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    roll_number: Optional[str] = None
    course_code: Optional[str] = None
    semester: Optional[int] = None
    subject_code: Optional[str] = None
    faculty_name: Optional[str] = None
    category: str = "CURRICULUM"  # CURRICULUM, TEACHING_METHODOLOGY, PRACTICUM_LAB, FACILITIES, GENERAL
    rating: int = Field(5, ge=1, le=5)
    comments: str
    is_anonymous: bool = False


class FeedbackRespond(BaseModel):
    response: str


class FeedbackResponse(BaseModel):
    id: str
    student_id: str
    student_name: str
    roll_number: str
    course_code: str
    semester: int
    subject_code: Optional[str] = None
    faculty_name: Optional[str] = None
    category: str
    rating: int
    comments: str
    is_anonymous: bool
    status: str
    created_at: str
    admin_response: Optional[str] = None


@router.get("", response_model=List[FeedbackResponse])
async def get_feedbacks(
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    db = DatabaseManager.get_database()
    query = {}
    if category and category != "ALL":
        query["category"] = category

    if is_student(current_user):
        st = await get_student_record(db, current_user, required=True)
        query["student_id"] = str(st["_id"])
    elif is_faculty(current_user):
        fac = await get_faculty_record(db, current_user)
        codes = [sub["code"] for sub in await get_faculty_subjects(db, fac)]
        query["$or"] = [{"faculty_name": (fac or {}).get("full_name", "__none__")}, {"subject_code": {"$in": codes}}]

    cursor = db.feedback.find(query).skip((page - 1) * limit).limit(limit).sort("created_at", -1)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.get("_id", doc.get("id", "")))
        if doc.get("is_anonymous") and current_user.get("role") != UserRole.SUPER_ADMIN:
            doc["student_name"] = "Anonymous Trainee"
            doc["roll_number"] = "ANON"
        results.append(doc)
    return results


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    data: FeedbackCreate,
    current_user: dict = Depends(get_current_user),
):
    db = DatabaseManager.get_database()
    doc = data.model_dump()

    if not is_student(current_user):
        raise HTTPException(status_code=403, detail="Only students can submit feedback.")
    if not (data.comments or "").strip():
        raise HTTPException(status_code=400, detail="Feedback comments are required.")
    st = await get_student_record(db, current_user, required=True)
    doc["student_id"] = str(st["_id"])
    doc["student_name"] = st.get("full_name", "")
    doc["roll_number"] = st.get("roll_number", "")
    doc["student_email"] = st.get("email")
    doc["course_code"] = st.get("course_code", "")
    doc["semester"] = st.get("semester", 1)

    doc["status"] = "PENDING"
    doc["created_at"] = datetime.utcnow().isoformat()
    doc["admin_response"] = None

    result = await db.feedback.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc



@router.post("/{feedback_id}/respond", response_model=FeedbackResponse)
async def respond_feedback(
    feedback_id: str,
    data: FeedbackRespond,
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY])),
):
    db = DatabaseManager.get_database()
    query = {"_id": oid(feedback_id)}

    update = {
        "$set": {
            "status": "RESOLVED",
            "admin_response": data.response,
            "responded_by": current_user.get("full_name"),
        }
    }

    res = await db.feedback.find_one_and_update(query, update, return_document=True)
    if not res:
        raise HTTPException(status_code=404, detail="Feedback entry not found")
    res["id"] = str(res.get("_id", res.get("id", "")))
    return res
