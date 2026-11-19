from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from annapurna_memorial_college_erp_backend.database import DatabaseManager

router = APIRouter(prefix="/feedback", tags=["Student Feedback"])


class FeedbackCreate(BaseModel):
    student_id: str
    student_name: str
    roll_number: str
    course_code: str = "BED"
    semester: int = 1
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
async def get_feedbacks(category: Optional[str] = None):
    db = DatabaseManager.get_database()
    query = {}
    if category:
        query["category"] = category

    cursor = db.feedback.find(query).sort("created_at", -1)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.get("_id", doc.get("id", "")))
        if doc.get("is_anonymous"):
            doc["student_name"] = "Anonymous Trainee"
            doc["roll_number"] = "ANON"
        results.append(doc)
    return results


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(data: FeedbackCreate):
    db = DatabaseManager.get_database()
    doc = data.model_dump()
    doc["status"] = "PENDING"
    doc["created_at"] = datetime.utcnow().isoformat()
    doc["admin_response"] = None

    result = await db.feedback.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return doc


@router.post("/{feedback_id}/respond", response_model=FeedbackResponse)
async def respond_feedback(feedback_id: str, data: FeedbackRespond):
    db = DatabaseManager.get_database()
    from bson import ObjectId

    try:
        obj_id = ObjectId(feedback_id)
        query = {"_id": obj_id}
    except Exception:
        query = {"id": feedback_id}

    update = {
        "$set": {
            "status": "RESOLVED",
            "admin_response": data.response,
        }
    }

    res = await db.feedback.find_one_and_update(query, update, return_document=True)
    if not res:
        raise HTTPException(status_code=404, detail="Feedback entry not found")
    res["id"] = str(res.get("_id", res.get("id", "")))
    return res
