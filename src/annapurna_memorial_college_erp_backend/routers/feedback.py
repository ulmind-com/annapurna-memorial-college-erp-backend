"""Student feedback cycles (college ERP / IQAC style).

Admin creates a feedback form for a course + semester with rating questions and opens it.
Each student of that class submits once, rating every subject/teacher of their semester.
Responses are anonymous: reports show only aggregates and comments, never who wrote them.
Teachers see the aggregated report for their own subjects only.
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import get_current_user, require_roles, UserRole
from annapurna_memorial_college_erp_backend.deps import (
    get_student_record, get_faculty_scope, student_user_ids, is_student, is_faculty, is_admin, oid,
)
from annapurna_memorial_college_erp_backend.services.notification_service import notification_service

router = APIRouter(prefix="/feedback", tags=["Student Feedback"])


class FormCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    course_code: str
    semester: int
    questions: List[str] = Field(..., min_length=1)
    deadline: Optional[str] = None  # YYYY-MM-DD
    is_open: bool = True


class FormUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    questions: Optional[List[str]] = None
    deadline: Optional[str] = None
    is_open: Optional[bool] = None


class SubjectRating(BaseModel):
    subject_code: str
    answers: List[int]  # one 1-5 rating per question, same order as form.questions


class ResponseSubmit(BaseModel):
    ratings: List[SubjectRating]
    comments: Optional[str] = ""


def _is_accepting(form: dict) -> bool:
    if not form.get("is_open"):
        return False
    deadline = form.get("deadline")
    return not deadline or datetime.now().strftime("%Y-%m-%d") <= deadline


async def _subjects_for(db, course_code: str, semester: int) -> list:
    return [
        {"subject_code": s["code"], "subject_title": s.get("title", s["code"]), "faculty_name": s.get("faculty_name"), "faculty_id": s.get("faculty_id")}
        async for s in db.subjects.find({"course_code": course_code, "semester": semester}).sort("code", 1)
    ]


async def _form_out(db, f: dict, student_id: Optional[str] = None) -> dict:
    form_id = str(f["_id"])
    out = {
        "id": form_id,
        "title": f["title"],
        "description": f.get("description", ""),
        "course_code": f["course_code"],
        "semester": f["semester"],
        "questions": f["questions"],
        "deadline": f.get("deadline"),
        "is_open": f.get("is_open", False),
        "accepting": _is_accepting(f),
        "created_at": f.get("created_at"),
        "response_count": await db.feedback_responses.count_documents({"form_id": form_id}),
        "class_size": await db.students.count_documents({"course_code": f["course_code"], "semester": f["semester"]}),
    }
    if student_id is not None:
        out["submitted"] = bool(await db.feedback_responses.find_one({"form_id": form_id, "student_id": student_id}, {"_id": 1}))
        out["subjects"] = await _subjects_for(db, f["course_code"], f["semester"])
    return out


@router.get("/forms")
async def list_forms(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    if is_student(current_user):
        st = await get_student_record(db, current_user, required=True)
        cursor = db.feedback_forms.find({"course_code": st.get("course_code"), "semester": st.get("semester", 1), "is_open": True})
        return [await _form_out(db, f, str(st["_id"])) async for f in cursor.sort("created_at", -1)]
    query: dict = {}
    if is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        if not scope["classes"]:
            return []
        query = {"$or": [{"course_code": c, "semester": s} for c, s in scope["classes"]]}
    return [await _form_out(db, f) async for f in db.feedback_forms.find(query).sort("created_at", -1)]


@router.post("/forms", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_form(req: FormCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    code = req.course_code.upper()
    questions = [q.strip() for q in req.questions if q.strip()]
    if not req.title.strip() or not questions:
        raise HTTPException(status_code=400, detail="Title and at least one question are required.")
    if not await db.subjects.count_documents({"course_code": code, "semester": req.semester}):
        raise HTTPException(status_code=400, detail=f"No subjects exist for {code} Semester {req.semester}.")
    doc = {
        **req.model_dump(),
        "title": req.title.strip(),
        "course_code": code,
        "questions": questions,
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc),
    }
    res = await db.feedback_forms.insert_one(doc)
    doc["_id"] = res.inserted_id
    if req.is_open:
        user_ids = await student_user_ids(db, {"course_code": code, "semester": req.semester})
        await notification_service.notify_users(
            db, user_ids, "Feedback open", f"Please submit: {doc['title']}", {"type": "FEEDBACK", "id": str(res.inserted_id)},
        )
    return await _form_out(db, doc)


@router.put("/forms/{form_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def update_form(form_id: str, req: FormUpdate):
    db = await get_db()
    f = await db.feedback_forms.find_one({"_id": oid(form_id)})
    if not f:
        raise HTTPException(status_code=404, detail="Feedback form not found.")
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if "questions" in update:
        if await db.feedback_responses.count_documents({"form_id": form_id}):
            raise HTTPException(status_code=400, detail="Questions cannot change after students have responded.")
        update["questions"] = [q.strip() for q in update["questions"] if q.strip()]
        if not update["questions"]:
            raise HTTPException(status_code=400, detail="At least one question is required.")
    await db.feedback_forms.update_one({"_id": f["_id"]}, {"$set": update})
    f.update(update)
    return await _form_out(db, f)


@router.delete("/forms/{form_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def delete_form(form_id: str):
    db = await get_db()
    res = await db.feedback_forms.delete_one({"_id": oid(form_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Feedback form not found.")
    await db.feedback_responses.delete_many({"form_id": form_id})
    return {"message": "Feedback form deleted."}


@router.post("/forms/{form_id}/submit", status_code=201)
async def submit_response(form_id: str, req: ResponseSubmit, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    if not is_student(current_user):
        raise HTTPException(status_code=403, detail="Only students can submit feedback.")
    f = await db.feedback_forms.find_one({"_id": oid(form_id)})
    if not f:
        raise HTTPException(status_code=404, detail="Feedback form not found.")
    st = await get_student_record(db, current_user, required=True)
    if (st.get("course_code"), st.get("semester", 1)) != (f["course_code"], f["semester"]):
        raise HTTPException(status_code=403, detail="This feedback form is not for your class.")
    if not _is_accepting(f):
        raise HTTPException(status_code=400, detail="This feedback form is closed.")
    student_id = str(st["_id"])
    if await db.feedback_responses.find_one({"form_id": form_id, "student_id": student_id}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="You have already submitted this feedback.")

    subjects = {s["subject_code"]: s for s in await _subjects_for(db, f["course_code"], f["semester"])}
    n_q = len(f["questions"])
    ratings = []
    for r in req.ratings:
        sub = subjects.get(r.subject_code.upper())
        if not sub:
            raise HTTPException(status_code=400, detail=f"Unknown subject {r.subject_code}.")
        if len(r.answers) != n_q or any(a < 1 or a > 5 for a in r.answers):
            raise HTTPException(status_code=400, detail=f"Rate every question 1-5 for {r.subject_code}.")
        ratings.append({"subject_code": sub["subject_code"], "faculty_name": sub.get("faculty_name"), "answers": r.answers})
    if {r["subject_code"] for r in ratings} != set(subjects):
        raise HTTPException(status_code=400, detail="Please rate all subjects.")

    await db.feedback_responses.insert_one({
        "form_id": form_id,
        "student_id": student_id,  # used only to enforce one response per student; never returned
        "ratings": ratings,
        "comments": (req.comments or "").strip(),
        "created_at": datetime.now(timezone.utc),
    })
    return {"message": "Thank you! Your feedback was submitted anonymously."}


@router.get("/forms/{form_id}/report")
async def form_report(form_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    if is_student(current_user):
        raise HTTPException(status_code=403, detail="Access denied.")
    f = await db.feedback_forms.find_one({"_id": oid(form_id)})
    if not f:
        raise HTTPException(status_code=404, detail="Feedback form not found.")
    allowed = None
    if is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        allowed = {s["code"] for s in scope["subjects"]}

    n_q = len(f["questions"])
    agg: dict = {}
    comments = []
    total = 0
    async for resp in db.feedback_responses.find({"form_id": form_id}):
        total += 1
        if resp.get("comments") and allowed is None:
            comments.append({"text": resp["comments"], "created_at": resp.get("created_at")})
        for r in resp.get("ratings", []):
            if allowed is not None and r["subject_code"] not in allowed:
                continue
            a = agg.setdefault(r["subject_code"], {"faculty_name": r.get("faculty_name"), "count": 0, "sums": [0] * n_q})
            a["count"] += 1
            for i, v in enumerate(r["answers"][:n_q]):
                a["sums"][i] += v

    subjects = []
    for s in await _subjects_for(db, f["course_code"], f["semester"]):
        if allowed is not None and s["subject_code"] not in allowed:
            continue
        a = agg.get(s["subject_code"], {"count": 0, "sums": [0] * n_q, "faculty_name": s.get("faculty_name")})
        avgs = [round(x / a["count"], 2) if a["count"] else 0 for x in a["sums"]]
        subjects.append({
            "subject_code": s["subject_code"],
            "subject_title": s["subject_title"],
            "faculty_name": a.get("faculty_name") or s.get("faculty_name"),
            "responses": a["count"],
            "question_averages": avgs,
            "overall_average": round(sum(avgs) / n_q, 2) if a["count"] else 0,
        })
    return {
        "form": await _form_out(db, f),
        "total_responses": total,
        "subjects": subjects,
        "comments": sorted(comments, key=lambda c: str(c["created_at"]), reverse=True),
    }
