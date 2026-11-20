from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from annapurna_memorial_college_erp_backend.database import DatabaseManager

router = APIRouter(prefix="/leaves", tags=["Leave Applications"])


class LeaveCreate(BaseModel):
    student_id: str
    student_name: str
    roll_number: str
    course_code: str = "BED"
    semester: int = 1
    leave_type: str = "MEDICAL"  # MEDICAL, PERSONAL, ACADEMIC, EMERGENCY
    start_date: str
    end_date: str
    total_days: int = 1
    reason: str


class LeaveReview(BaseModel):
    status: str  # APPROVED, REJECTED
    remarks: str
    reviewer_name: str


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


@router.get("", response_model=List[LeaveResponse])
async def get_leaves(student_id: Optional[str] = None):
    db = DatabaseManager.get_database()
    query = {}
    if student_id:
        query["$or"] = [{"student_id": student_id}, {"roll_number": student_id}]

    cursor = db.leaves.find(query).sort("applied_at", -1)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.get("_id", doc.get("id", "")))
        results.append(doc)
    return results


@router.post("", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
async def apply_leave(data: LeaveCreate):
    db = DatabaseManager.get_database()
    doc = data.model_dump()
    doc["status"] = "PENDING"
    doc["applied_at"] = datetime.utcnow().isoformat()
    doc["reviewed_by"] = None
    doc["reviewed_at"] = None
    doc["remarks"] = None

    result = await db.leaves.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


@router.post("/{leave_id}/review", response_model=LeaveResponse)
async def review_leave(leave_id: str, data: LeaveReview):
    db = DatabaseManager.get_database()
    from bson import ObjectId

    try:
        obj_id = ObjectId(leave_id)
        query = {"_id": obj_id}
    except Exception:
        query = {"id": leave_id}

    update = {
        "$set": {
            "status": data.status,
            "remarks": data.remarks,
            "reviewed_by": data.reviewer_name,
            "reviewed_at": datetime.utcnow().isoformat(),
        }
    }

    res = await db.leaves.find_one_and_update(query, update, return_document=True)
    if not res:
        raise HTTPException(status_code=404, detail="Leave application not found")
    res["id"] = str(res.get("_id", res.get("id", "")))
    return res
