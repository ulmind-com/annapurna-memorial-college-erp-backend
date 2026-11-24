from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    UserRole,
)

router = APIRouter(prefix="/assignments", tags=["Assignments & Practicum"])


class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    course_code: str
    semester: int = 1
    due_date: str  # YYYY-MM-DD
    due_time: Optional[str] = "17:00"  # HH:MM
    max_marks: int = 25
    weightage: Optional[str] = "Continuous Evaluation"


class AssignmentSubmit(BaseModel):
    submission_text: Optional[str] = ""
    file_url: Optional[str] = ""
    file_name: Optional[str] = ""
    comments: Optional[str] = ""


class AssignmentGrade(BaseModel):
    marks_awarded: float
    feedback: Optional[str] = ""


@router.get("")
async def list_assignments(
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}

    student_record = None
    is_student = current_user.get("role") == UserRole.STUDENT

    if is_student:
        student_record = await db.students.find_one({
            "$or": [
                {"email": current_user.get("email")},
                {"_id": ObjectId(current_user["id"]) if ObjectId.is_valid(current_user.get("id", "")) else None},
            ]
        })
        if student_record and not course_code:
            course_code = student_record.get("course_code") or student_record.get("course")
            if not semester:
                semester = student_record.get("semester", 1)

    if course_code and course_code != "ALL":
        query["course_code"] = course_code.upper()
    if semester:
        query["semester"] = int(semester)

    cursor = db.assignments.find(query).sort("created_at", -1)
    assignments = []
    async for a in cursor:
        a_id = str(a["_id"])
        
        # Count total submissions
        sub_count = await db.assignment_submissions.count_documents({"assignment_id": a_id})
        
        # Total assigned calculation
        total_assigned = a.get("total_assigned", 50)
        pending_count = max(0, total_assigned - sub_count)

        # Check this user's submission if student
        user_submission = None
        if is_student and student_record:
            st_id = str(student_record["_id"])
            st_roll = student_record.get("roll_number")
            sub_doc = await db.assignment_submissions.find_one({
                "assignment_id": a_id,
                "$or": [
                    {"student_id": st_id},
                    {"roll_number": st_roll},
                    {"student_email": current_user.get("email")},
                ]
            })
            if sub_doc:
                user_submission = {
                    "id": str(sub_doc["_id"]),
                    "status": sub_doc.get("status", "SUBMITTED"),
                    "submitted_at": sub_doc.get("submitted_at"),
                    "marks_awarded": sub_doc.get("marks_awarded"),
                    "feedback": sub_doc.get("feedback"),
                    "file_url": sub_doc.get("file_url"),
                    "submission_text": sub_doc.get("submission_text"),
                }

        assignments.append({
            "id": a_id,
            "title": a["title"],
            "description": a.get("description", ""),
            "course": a.get("course_name") or f"{a['course_code']} Sem {a['semester']}",
            "courseCode": a["course_code"],
            "semester": a["semester"],
            "dueDate": a["due_date"],
            "dueTime": a.get("due_time", "17:00"),
            "totalAssigned": total_assigned,
            "submittedCount": sub_count,
            "pendingCount": pending_count,
            "overdueCount": a.get("overdue_count", 0),
            "maxMarks": a.get("max_marks", 25),
            "weightage": a.get("weightage", "Continuous Evaluation"),
            "status": a.get("status", "ACTIVE"),
            "created_by": a.get("created_by"),
            "creator_name": a.get("creator_name", "Faculty Member"),
            "created_at": a.get("created_at"),
            "user_submission": user_submission,
        })
    return assignments


@router.post("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def create_assignment(req: AssignmentCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    c_code = req.course_code.upper()

    course_obj = await db.courses.find_one({"code": c_code})
    course_name = course_obj.get("name") if course_obj else f"{c_code} Program"
    max_intake = course_obj.get("max_intake", 50) if course_obj else 50

    # Count enrolled students
    enrolled_count = await db.students.count_documents({
        "$or": [
            {"course_code": c_code},
            {"course": c_code},
            {"course_name": {"$regex": course_name, "$options": "i"}} if course_name else {"course_code": c_code},
        ]
    })
    total_assigned = enrolled_count if enrolled_count > 0 else max_intake

    doc = {
        "title": req.title.strip(),
        "description": (req.description or "").strip(),
        "course_code": c_code,
        "course_name": f"{course_name} Sem {req.semester}",
        "semester": req.semester,
        "due_date": req.due_date,
        "due_time": req.due_time or "17:00",
        "total_assigned": total_assigned,
        "max_marks": req.max_marks,
        "weightage": req.weightage or "Continuous Evaluation",
        "status": "ACTIVE",
        "created_by": current_user.get("id"),
        "creator_name": current_user.get("full_name", "Faculty Member"),
        "created_at": datetime.now(timezone.utc),
    }

    res = await db.assignments.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["course"] = doc["course_name"]
    doc["courseCode"] = doc["course_code"]
    doc["dueDate"] = doc["due_date"]
    doc["dueTime"] = doc["due_time"]
    doc["totalAssigned"] = doc["total_assigned"]
    doc["submittedCount"] = 0
    doc["pendingCount"] = doc["total_assigned"]
    doc["overdueCount"] = 0
    doc["maxMarks"] = doc["max_marks"]
    doc.pop("_id", None)
    return doc


@router.delete("/{assignment_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def delete_assignment(assignment_id: str):
    db = await get_db()
    try:
        q = {"_id": ObjectId(assignment_id)}
    except Exception:
        q = {"id": assignment_id}

    res = await db.assignments.delete_one(q)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    await db.assignment_submissions.delete_many({"assignment_id": assignment_id})
    return {"message": "Assignment deleted successfully."}


@router.post("/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: str,
    req: AssignmentSubmit,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    try:
        a_q = {"_id": ObjectId(assignment_id)}
    except Exception:
        a_q = {"id": assignment_id}

    assignment = await db.assignments.find_one(a_q)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")

    # Find student details
    student = await db.students.find_one({
        "$or": [
            {"email": current_user.get("email")},
            {"_id": ObjectId(current_user["id"]) if ObjectId.is_valid(current_user.get("id", "")) else None},
        ]
    })

    student_id = str(student["_id"]) if student else current_user.get("id")
    student_name = student.get("full_name") if student else current_user.get("full_name", "Student")
    roll_number = student.get("roll_number") if student else "AMC-STU"

    sub_doc = {
        "assignment_id": assignment_id,
        "student_id": student_id,
        "student_name": student_name,
        "student_email": current_user.get("email"),
        "roll_number": roll_number,
        "submission_text": (req.submission_text or "").strip(),
        "file_url": (req.file_url or "").strip(),
        "file_name": (req.file_name or "").strip(),
        "comments": (req.comments or "").strip(),
        "submitted_at": datetime.now(timezone.utc),
        "status": "SUBMITTED",
        "marks_awarded": None,
        "feedback": None,
    }

    # Upsert submission
    res = await db.assignment_submissions.update_one(
        {"assignment_id": assignment_id, "student_id": student_id},
        {"$set": sub_doc},
        upsert=True,
    )

    return {"message": "Assignment submitted successfully.", "status": "SUBMITTED"}


@router.get("/{assignment_id}/submissions", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def list_assignment_submissions(assignment_id: str):
    db = await get_db()
    cursor = db.assignment_submissions.find({"assignment_id": assignment_id}).sort("submitted_at", -1)
    submissions = []
    async for s in cursor:
        submissions.append({
            "id": str(s["_id"]),
            "assignment_id": s["assignment_id"],
            "student_id": s["student_id"],
            "student_name": s["student_name"],
            "student_email": s.get("student_email"),
            "roll_number": s["roll_number"],
            "submission_text": s.get("submission_text"),
            "file_url": s.get("file_url"),
            "file_name": s.get("file_name"),
            "comments": s.get("comments"),
            "submitted_at": s.get("submitted_at"),
            "status": s.get("status", "SUBMITTED"),
            "marks_awarded": s.get("marks_awarded"),
            "feedback": s.get("feedback"),
        })
    return submissions


@router.post("/submissions/{submission_id}/grade", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def grade_assignment_submission(
    submission_id: str,
    req: AssignmentGrade,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    try:
        q = {"_id": ObjectId(submission_id)}
    except Exception:
        q = {"id": submission_id}

    update_doc = {
        "marks_awarded": req.marks_awarded,
        "feedback": (req.feedback or "").strip(),
        "status": "GRADED",
        "graded_at": datetime.now(timezone.utc),
        "graded_by": current_user.get("full_name", "Faculty Member"),
    }

    res = await db.assignment_submissions.update_one(q, {"$set": update_doc})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Submission not found.")

    return {"message": "Assignment graded successfully.", **update_doc}
