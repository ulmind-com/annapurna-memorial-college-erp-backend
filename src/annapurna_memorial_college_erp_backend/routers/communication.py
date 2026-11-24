"""Class announcements (teacher -> class) and student queries (student <-> teacher)."""
from datetime import datetime, timezone
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import get_current_user, require_roles, UserRole
from annapurna_memorial_college_erp_backend.deps import (
    get_student_record, get_faculty_scope, classes_query, student_user_ids,
    is_student, is_faculty, is_admin, oid,
)
from annapurna_memorial_college_erp_backend.services.notification_service import notification_service
from annapurna_memorial_college_erp_backend.services.storage_service import storage_service

router = APIRouter(tags=["Class Communication"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class AnnouncementCreate(BaseModel):
    course_code: str
    semester: int
    subject_code: Optional[str] = None
    batch: Optional[str] = "All Sections"
    title: str
    message: str
    priority: Literal["NORMAL", "IMPORTANT", "URGENT"] = "NORMAL"


class QueryCreate(BaseModel):
    subject_code: Optional[str] = None
    question: str


class QueryReply(BaseModel):
    reply: str


def _ann_out(a: dict) -> dict:
    return {
        "id": str(a["_id"]),
        "faculty_id": a.get("faculty_id", ""),
        "faculty_name": a.get("faculty_name", ""),
        "course_code": a.get("course_code", ""),
        "semester": a.get("semester", 1),
        "subject_code": a.get("subject_code"),
        "batch": a.get("batch"),
        "title": a.get("title", ""),
        "message": a.get("message", ""),
        "priority": a.get("priority", "NORMAL"),
        "created_at": a.get("created_at"),
    }


@router.get("/announcements")
async def list_announcements(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    query: dict = {}
    if is_student(current_user):
        st = await get_student_record(db, current_user, required=True)
        query = {"course_code": st.get("course_code"), "semester": st.get("semester", 1)}
    elif is_faculty(current_user):
        query = {"created_by": current_user["id"]}
    return [_ann_out(a) async for a in db.announcements.find(query).sort("created_at", -1).limit(300)]


@router.post("/announcements", dependencies=[Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_announcement(req: AnnouncementCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    code = req.course_code.upper()
    if not req.title.strip() or not req.message.strip():
        raise HTTPException(status_code=400, detail="Title and message are required.")
    scope = await get_faculty_scope(db, current_user)
    if is_faculty(current_user) and (code, req.semester) not in scope["classes"]:
        raise HTTPException(status_code=403, detail="You can only announce to your assigned classes.")

    doc = {
        **req.model_dump(),
        "course_code": code,
        "subject_code": (req.subject_code or "").upper() or None,
        "title": req.title.strip(),
        "message": req.message.strip(),
        "faculty_id": str(scope["faculty"]["_id"]) if scope["faculty"] else current_user["id"],
        "faculty_name": current_user.get("full_name", ""),
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc),
    }
    res = await db.announcements.insert_one(doc)
    doc["_id"] = res.inserted_id
    user_ids = await student_user_ids(db, {"course_code": code, "semester": req.semester})
    await notification_service.notify_users(
        db, user_ids, f"{doc['faculty_name']}: {doc['title']}", doc["message"][:150],
        {"type": "ANNOUNCEMENT", "id": str(res.inserted_id)},
    )
    return _ann_out(doc)


@router.delete("/announcements/{ann_id}", dependencies=[Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def delete_announcement(ann_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    a = await db.announcements.find_one({"_id": oid(ann_id)})
    if not a:
        raise HTTPException(status_code=404, detail="Announcement not found.")
    if not is_admin(current_user) and a.get("created_by") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied.")
    await db.announcements.delete_one({"_id": a["_id"]})
    return {"message": "Announcement deleted."}


# ---------------- STUDENT QUERIES ----------------

def _q_out(q: dict) -> dict:
    return {
        "id": str(q["_id"]),
        "student_id": q.get("student_id"),
        "student_name": q.get("student_name"),
        "roll_number": q.get("roll_number"),
        "course_code": q.get("course_code"),
        "semester": q.get("semester"),
        "subject_code": q.get("subject_code"),
        "question": q.get("question"),
        "reply": q.get("reply"),
        "replied_by": q.get("replied_by"),
        "replied_at": q.get("replied_at"),
        "status": q.get("status", "OPEN"),
        "created_at": q.get("created_at"),
    }


@router.get("/queries")
async def list_queries(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    query: dict = {}
    if is_student(current_user):
        st = await get_student_record(db, current_user, required=True)
        query = {"student_id": str(st["_id"])}
    elif is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        query = classes_query(scope["classes"])
    return [_q_out(q) async for q in db.student_queries.find(query).sort("created_at", -1).limit(500)]


@router.post("/queries")
async def create_query(req: QueryCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    if not is_student(current_user):
        raise HTTPException(status_code=403, detail="Only students can raise queries.")
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question is required.")
    st = await get_student_record(db, current_user, required=True)
    doc = {
        "student_id": str(st["_id"]),
        "student_name": st.get("full_name"),
        "roll_number": st.get("roll_number"),
        "course_code": st.get("course_code"),
        "semester": st.get("semester", 1),
        "subject_code": (req.subject_code or "").upper() or None,
        "question": req.question.strip(),
        "status": "OPEN",
        "created_at": datetime.now(timezone.utc),
    }
    res = await db.student_queries.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _q_out(doc)


@router.post("/queries/{query_id}/reply", dependencies=[Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def reply_query(query_id: str, req: QueryReply, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    q = await db.student_queries.find_one({"_id": oid(query_id)})
    if not q:
        raise HTTPException(status_code=404, detail="Query not found.")
    if is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        if (q.get("course_code"), q.get("semester")) not in scope["classes"]:
            raise HTTPException(status_code=403, detail="This student is not in your classes.")
    if not req.reply.strip():
        raise HTTPException(status_code=400, detail="Reply is required.")
    update = {
        "reply": req.reply.strip(),
        "replied_by": current_user.get("full_name"),
        "replied_at": datetime.now(timezone.utc),
        "status": "ANSWERED",
    }
    await db.student_queries.update_one({"_id": q["_id"]}, {"$set": update})
    q.update(update)
    user_ids = [str(u["_id"]) async for u in db.users.find({"entity_id": q.get("student_id")}, {"_id": 1})]
    await notification_service.notify_users(
        db, user_ids, "Your query was answered", update["reply"][:150], {"type": "QUERY", "id": query_id},
    )
    return _q_out(q)


# ---------------- GENERIC FILE UPLOAD ----------------

@router.post("/uploads")
async def upload_file(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Upload a document (e.g. assignment answer PDF) and return its URL."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 15 MB).")
    url = await storage_service.upload_file(data, filename=file.filename or "upload", folder="uploads")
    return {"url": url, "file_name": file.filename, "size": len(data)}
