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

router = APIRouter(prefix="/study-materials", tags=["Digital Library & Study Materials"])


@router.get("")
async def list_study_materials(
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    subject_code: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if course_code:
        query["course_code"] = course_code
    if semester:
        query["semester"] = semester
    if subject_code:
        query["subject_code"] = subject_code

    cursor = db.study_materials.find(query).sort("created_at", -1)
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
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
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
        file_url = "/uploads/study_materials_document.pdf"
        file_type = "pdf"
        file_size_bytes = 1024 * 128

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
        "uploaded_by_id": current_user["id"],
        "uploaded_by_name": current_user.get("name") or current_user.get("full_name") or "Faculty Member",
        "downloads_count": 0,
        "created_at": datetime.now(timezone.utc),
    }

    res = await db.study_materials.insert_one(doc)
    return {"id": str(res.inserted_id), **doc}


@router.post("/{material_id}/download")
async def track_download(material_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    await db.study_materials.update_one(
        {"_id": ObjectId(material_id)},
        {"$inc": {"downloads_count": 1}},
    )
    return {"message": "Download tracked"}
