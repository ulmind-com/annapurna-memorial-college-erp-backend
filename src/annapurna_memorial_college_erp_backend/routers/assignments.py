from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.deps import (
    get_student_record, get_faculty_scope, classes_query, student_user_ids, is_student, is_faculty, is_admin, oid,
)
from annapurna_memorial_college_erp_backend.services.notification_service import notification_service
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
    max_marks: int = Field(25, ge=1, le=1000)
    weightage: Optional[str] = "Continuous Evaluation"
    subject_code: Optional[str] = None
    attachment_url: Optional[str] = None


class AssignmentSubmit(BaseModel):
    submission_text: Optional[str] = ""
    file_url: Optional[str] = ""
    file_name: Optional[str] = ""
    comments: Optional[str] = ""


class AssignmentGrade(BaseModel):
    marks_awarded: float
    feedback: Optional[str] = ""


def _aq(assignment_id: str) -> dict:
    return {"_id": oid(assignment_id)}


async def _can_manage(db, current_user: dict, assignment: dict) -> bool:
    if is_admin(current_user):
        return True
    if assignment.get("created_by") == current_user.get("id"):
        return True
    scope = await get_faculty_scope(db, current_user)
    return (assignment.get("course_code"), assignment.get("semester")) in scope["classes"]


def _is_overdue(a: dict) -> bool:
    try:
        due = datetime.fromisoformat(f"{a['due_date']}T{a.get('due_time') or '23:59'}")
        return datetime.now() > due
    except Exception:
        return False


@router.get("")
async def list_assignments(
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query: dict = {}
    student_record = None

    if is_student(current_user):
        student_record = await get_student_record(db, current_user, required=True)
        query["course_code"] = student_record.get("course_code")
        query["semester"] = student_record.get("semester", 1)
    else:
        if is_faculty(current_user):
            scope = await get_faculty_scope(db, current_user)
            or_conds = classes_query(scope["classes"]).get("$or", [])
            or_conds.append({"created_by": current_user.get("id")})
            query["$or"] = or_conds
        if course_code and course_code != "ALL":
            query["course_code"] = course_code.upper()
        if semester:
            query["semester"] = int(semester)

    cursor = db.assignments.find(query).sort("created_at", -1)
    assignments = []
    async for a in cursor:
        a_id = str(a["_id"])
        sub_count = await db.assignment_submissions.count_documents({"assignment_id": a_id})
        graded_count = await db.assignment_submissions.count_documents({"assignment_id": a_id, "status": "GRADED"})
        total_assigned = await db.students.count_documents({"course_code": a["course_code"], "semester": a["semester"]})
        pending_count = max(0, total_assigned - sub_count)
        overdue = _is_overdue(a)

        user_submission = None
        if student_record:
            sub_doc = await db.assignment_submissions.find_one({
                "assignment_id": a_id, "student_id": str(student_record["_id"]),
            })
            if sub_doc:
                user_submission = {
                    "id": str(sub_doc["_id"]),
                    "status": sub_doc.get("status", "SUBMITTED"),
                    "submitted_at": sub_doc.get("submitted_at"),
                    "marks_awarded": sub_doc.get("marks_awarded"),
                    "feedback": sub_doc.get("feedback"),
                    "file_url": sub_doc.get("file_url"),
                    "file_name": sub_doc.get("file_name"),
                    "submission_text": sub_doc.get("submission_text"),
                    "is_late": sub_doc.get("is_late", False),
                }

        assignments.append({
            "id": a_id,
            "title": a["title"],
            "description": a.get("description", ""),
            "course": a.get("course_name") or f"{a['course_code']} Sem {a['semester']}",
            "courseCode": a["course_code"],
            "semester": a["semester"],
            "subjectCode": a.get("subject_code"),
            "dueDate": a["due_date"],
            "dueTime": a.get("due_time", "17:00"),
            "totalAssigned": total_assigned,
            "submittedCount": sub_count,
            "gradedCount": graded_count,
            "pendingCount": pending_count,
            "overdueCount": pending_count if overdue else 0,
            "isOverdue": overdue,
            "maxMarks": a.get("max_marks", 25),
            "weightage": a.get("weightage", "Continuous Evaluation"),
            "attachmentUrl": a.get("attachment_url"),
            "status": "CLOSED" if overdue else a.get("status", "ACTIVE"),
            "created_by": a.get("created_by"),
            "creator_name": a.get("creator_name", ""),
            "created_at": a.get("created_at"),
            "user_submission": user_submission,
        })
    return assignments


@router.post("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def create_assignment(req: AssignmentCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    c_code = req.course_code.upper()
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Title is required.")
    course_obj = await db.courses.find_one({"code": c_code})
    if not course_obj:
        raise HTTPException(status_code=400, detail=f"Course '{c_code}' does not exist.")
    if is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        if (c_code, req.semester) not in scope["classes"]:
            raise HTTPException(status_code=403, detail="You can only create assignments for your assigned classes.")

    doc = {
        "title": req.title.strip(),
        "description": (req.description or "").strip(),
        "course_code": c_code,
        "course_name": f"{course_obj.get('name', c_code)} Sem {req.semester}",
        "semester": req.semester,
        "subject_code": (req.subject_code or "").upper() or None,
        "due_date": req.due_date,
        "due_time": req.due_time or "17:00",
        "max_marks": req.max_marks,
        "weightage": req.weightage or "Continuous Evaluation",
        "attachment_url": req.attachment_url,
        "status": "ACTIVE",
        "created_by": current_user.get("id"),
        "creator_name": current_user.get("full_name", ""),
        "created_at": datetime.now(timezone.utc),
    }
    res = await db.assignments.insert_one(doc)
    doc.pop("_id", None)

    user_ids = await student_user_ids(db, {"course_code": c_code, "semester": req.semester})
    await notification_service.notify_users(
        db, user_ids, f"New Assignment: {doc['title']}",
        f"Due {doc['due_date']} {doc['due_time']}. Max marks {doc['max_marks']}.",
        {"type": "ASSIGNMENT", "id": str(res.inserted_id)},
    )
    return {"id": str(res.inserted_id), **doc}


@router.delete("/{assignment_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def delete_assignment(assignment_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    a = await db.assignments.find_one(_aq(assignment_id))
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if not await _can_manage(db, current_user, a):
        raise HTTPException(status_code=403, detail="You cannot delete this assignment.")
    await db.assignments.delete_one({"_id": a["_id"]})
    await db.assignment_submissions.delete_many({"assignment_id": assignment_id})
    return {"message": "Assignment deleted successfully."}


@router.post("/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: str,
    req: AssignmentSubmit,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    if not is_student(current_user):
        raise HTTPException(status_code=403, detail="Only students can submit assignments.")
    assignment = await db.assignments.find_one(_aq(assignment_id))
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    student = await get_student_record(db, current_user, required=True)
    if (student.get("course_code"), student.get("semester", 1)) != (assignment["course_code"], assignment["semester"]):
        raise HTTPException(status_code=403, detail="This assignment is not for your class.")
    if not (req.file_url or "").strip() and not (req.submission_text or "").strip():
        raise HTTPException(status_code=400, detail="Attach a file or write your answer before submitting.")

    student_id = str(student["_id"])
    existing = await db.assignment_submissions.find_one({"assignment_id": assignment_id, "student_id": student_id})
    if existing and existing.get("status") == "GRADED":
        raise HTTPException(status_code=400, detail="This assignment is already graded and cannot be resubmitted.")

    sub_doc = {
        "assignment_id": assignment_id,
        "student_id": student_id,
        "student_name": student.get("full_name", ""),
        "student_email": student.get("email"),
        "roll_number": student.get("roll_number", ""),
        "submission_text": (req.submission_text or "").strip(),
        "file_url": (req.file_url or "").strip(),
        "file_name": (req.file_name or "").strip(),
        "comments": (req.comments or "").strip(),
        "submitted_at": datetime.now(timezone.utc),
        "is_late": _is_overdue(assignment),
        "status": "SUBMITTED",
        "marks_awarded": None,
        "feedback": None,
    }
    await db.assignment_submissions.update_one(
        {"assignment_id": assignment_id, "student_id": student_id},
        {"$set": sub_doc},
        upsert=True,
    )
    return {"message": "Assignment submitted successfully.", "status": "SUBMITTED", "is_late": sub_doc["is_late"]}


@router.get("/{assignment_id}/submissions", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def list_assignment_submissions(assignment_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    a = await db.assignments.find_one(_aq(assignment_id))
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if not await _can_manage(db, current_user, a):
        raise HTTPException(status_code=403, detail="Access denied.")
    cursor = db.assignment_submissions.find({"assignment_id": assignment_id}).sort("submitted_at", -1)
    submissions = []
    async for s in cursor:
        submissions.append({
            "id": str(s["_id"]),
            "assignment_id": s["assignment_id"],
            "student_id": s["student_id"],
            "student_name": s.get("student_name", ""),
            "student_email": s.get("student_email"),
            "roll_number": s.get("roll_number", ""),
            "submission_text": s.get("submission_text"),
            "file_url": s.get("file_url"),
            "file_name": s.get("file_name"),
            "comments": s.get("comments"),
            "submitted_at": s.get("submitted_at"),
            "is_late": s.get("is_late", False),
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
    sub = await db.assignment_submissions.find_one({"_id": oid(submission_id)})
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    a = await db.assignments.find_one(_aq(sub["assignment_id"]))
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if not await _can_manage(db, current_user, a):
        raise HTTPException(status_code=403, detail="Access denied.")
    if req.marks_awarded < 0 or req.marks_awarded > a.get("max_marks", 25):
        raise HTTPException(status_code=400, detail=f"Marks must be between 0 and {a.get('max_marks', 25)}.")

    update_doc = {
        "marks_awarded": req.marks_awarded,
        "feedback": (req.feedback or "").strip(),
        "status": "GRADED",
        "graded_at": datetime.now(timezone.utc),
        "graded_by": current_user.get("full_name", ""),
    }
    await db.assignment_submissions.update_one({"_id": sub["_id"]}, {"$set": update_doc})
    user_ids = [str(u["_id"]) async for u in db.users.find({"entity_id": sub["student_id"]}, {"_id": 1})]
    await notification_service.notify_users(
        db, user_ids, f"Assignment Graded: {a['title']}",
        f"You scored {req.marks_awarded}/{a.get('max_marks', 25)}.",
        {"type": "ASSIGNMENT_GRADED", "id": sub["assignment_id"]},
    )
    return {"message": "Assignment graded successfully.", **update_doc}
