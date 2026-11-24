from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    UserRole,
)
from annapurna_memorial_college_erp_backend.services.storage_service import storage_service
from annapurna_memorial_college_erp_backend.services.notification_service import notification_service
from annapurna_memorial_college_erp_backend.deps import (
    get_student_record, get_faculty_scope, classes_query, student_user_ids, is_student, is_faculty, oid,
)

router = APIRouter(prefix="/study-materials", tags=["Digital Library & Study Materials"])


@router.get("")
async def list_study_materials(
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    subject_code: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if is_student(current_user):
        st = await get_student_record(db, current_user, required=True)
        course_code, semester = st.get("course_code"), st.get("semester", 1)
        query["category"] = {"$ne": "LESSON_PLAN"}
    elif is_faculty(current_user) and not course_code:
        scope = await get_faculty_scope(db, current_user)
        or_conds = classes_query(scope["classes"]).get("$or", [])
        or_conds.append({"uploaded_by_id": current_user.get("id")})
        query["$and"] = [{"$or": or_conds}]
    if category:
        query["category"] = category
    if course_code:
        query["course_code"] = course_code.upper()
    if semester:
        query["semester"] = semester
    if subject_code:
        query["subject_code"] = subject_code
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]

    cursor = db.study_materials.find(query).skip((page - 1) * limit).limit(limit).sort("created_at", -1)
    materials = []
    async for m in cursor:
        materials.append({
            "id": str(m["_id"]),
            "title": m["title"],
            "description": m.get("description"),
            "course_code": m["course_code"],
            "semester": m["semester"],
            "subject_code": m["subject_code"],
            "file_url": m["file_url"],
            "file_type": m.get("file_type", "pdf"),
            "file_size_bytes": m.get("file_size_bytes", 0),
            "tags": m.get("tags", []),
            "category": m.get("category", "NOTES"),
            "uploaded_by_id": m.get("uploaded_by_id"),
            "uploaded_by_name": m.get("uploaded_by_name", "Faculty"),
            "downloads_count": m.get("downloads_count", 0),
            "created_at": m.get("created_at"),
        })
    return materials


@router.post("", dependencies=[Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def upload_study_material(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    course_code: str = Form(...),
    semester: int = Form(...),
    subject_code: str = Form(...),
    tags: str = Form(""),  # comma separated
    category: str = Form("NOTES"),  # NOTES, PDF, LESSON_PLAN, SYLLABUS
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    if is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        if (course_code.upper(), semester) not in scope["classes"]:
            raise HTTPException(status_code=403, detail="You can only upload material for your assigned classes.")
    file_url = ""
    file_type = "pdf"
    file_size_bytes = 0

    if file and file.filename:
        file_bytes = await file.read()
        file_url = await storage_service.upload_file(
            file_bytes,
            filename=file.filename,
            folder="study_materials",
        )
        file_type = file.filename.split(".")[-1].lower() if "." in file.filename else "pdf"
        file_size_bytes = len(file_bytes)
    else:
        raise HTTPException(status_code=400, detail="Please attach a file to upload.")

    doc = {
        "title": title,
        "description": description,
        "course_code": course_code.upper(),
        "semester": semester,
        "subject_code": subject_code.upper(),
        "file_url": file_url,
        "file_type": file_type,
        "file_size_bytes": file_size_bytes,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "category": (category or "NOTES").upper(),
        "uploaded_by_id": current_user["id"],
        "uploaded_by_name": current_user.get("name") or current_user.get("full_name") or "Faculty Member",
        "downloads_count": 0,
        "created_at": datetime.now(timezone.utc),
    }

    res = await db.study_materials.insert_one(doc)
    doc.pop("_id", None)
    if doc["category"] != "LESSON_PLAN":
        user_ids = await student_user_ids(db, {"course_code": doc["course_code"], "semester": semester})
        await notification_service.notify_users(
            db, user_ids, f"New Study Material: {title}", f"{doc['subject_code']} - uploaded by {doc['uploaded_by_name']}",
            {"type": "STUDY_MATERIAL", "id": str(res.inserted_id)},
        )
    return {"id": str(res.inserted_id), **doc}


@router.delete("/{material_id}", dependencies=[Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def delete_study_material(material_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    m = await db.study_materials.find_one({"_id": oid(material_id)})
    if not m:
        raise HTTPException(status_code=404, detail="Material not found.")
    if is_faculty(current_user) and m.get("uploaded_by_id") != current_user.get("id"):
        raise HTTPException(status_code=403, detail="You can only delete material you uploaded.")
    await db.study_materials.delete_one({"_id": m["_id"]})
    return {"message": "Material deleted successfully."}


@router.post("/{material_id}/download")
async def track_download(material_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    await db.study_materials.update_one(
        {"_id": ObjectId(material_id)},
        {"$inc": {"downloads_count": 1}},
    )
    return {"message": "Download tracked"}
