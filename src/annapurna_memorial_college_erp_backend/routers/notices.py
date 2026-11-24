from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.notice import (
    NoticeCreate,
    NoticeUpdate,
    NoticeResponse,
    NoticeCategory,
    TargetAudience,
)
from annapurna_memorial_college_erp_backend.services.email_service import email_service
from annapurna_memorial_college_erp_backend.services.notification_service import notification_service
from annapurna_memorial_college_erp_backend.services.audit_service import audit_service

from annapurna_memorial_college_erp_backend.deps import is_faculty, oid

router = APIRouter(prefix="/notices", tags=["Notices & Circulars"])


@router.get("")
async def list_notices(
    category: Optional[NoticeCategory] = None,
    target_audience: Optional[TargetAudience] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if category:
        query["category"] = category.value
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"content": {"$regex": search, "$options": "i"}},
        ]

    user_role = current_user.get("role", "STUDENT")
    if target_audience:
        query["target_audience"] = target_audience.value
    elif user_role == UserRole.STUDENT.value:
        query["target_audience"] = {"$in": ["ALL", "STUDENTS"]}
    elif user_role == UserRole.FACULTY.value:
        query["target_audience"] = {"$in": ["ALL", "FACULTY"]}

    cursor = db.notices.find(query).skip((page - 1) * limit).limit(limit).sort([("is_pinned", -1), ("created_at", -1)])
    notices = []
    async for n in cursor:
        notices.append({
            "id": str(n["_id"]),
            "title": n["title"],
            "content": n["content"],
            "category": n.get("category", "ACADEMIC"),
            "target_audience": n.get("target_audience", "ALL"),
            "priority": n.get("priority", "NORMAL"),
            "is_pinned": n.get("is_pinned", False),
            "attachment_url": n.get("attachment_url"),
            "published_by_id": n.get("published_by_id", ""),
            "published_by_name": n.get("published_by_name", "College Administration"),
            "views_count": n.get("views_count", 0),
            "created_at": n.get("created_at"),
            "updated_at": n.get("updated_at"),
        })
    return notices


@router.post("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def create_notice(req: NoticeCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    doc = req.model_dump()
    doc["category"] = doc["category"].value if hasattr(doc["category"], "value") else doc["category"]
    doc["target_audience"] = doc["target_audience"].value if hasattr(doc["target_audience"], "value") else doc["target_audience"]
    doc["priority"] = doc["priority"].value if hasattr(doc["priority"], "value") else doc["priority"]
    doc["published_by_id"] = current_user["id"]
    doc["published_by_name"] = current_user.get("full_name") or "College Office"
    doc["views_count"] = 0
    doc["created_at"] = datetime.now(timezone.utc)

    res = await db.notices.insert_one(doc)
    notice_id = str(res.inserted_id)

    # Push notification to every targeted user's registered devices
    if req.send_push:
        role_filter = {}
        if req.target_audience.value == "STUDENTS":
            role_filter = {"role": "STUDENT"}
        elif req.target_audience.value == "FACULTY":
            role_filter = {"role": "FACULTY"}
        user_ids = [str(u["_id"]) async for u in db.users.find(role_filter, {"_id": 1})]
        await notification_service.notify_users(
            db, user_ids, f"Notice: {req.title}",
            req.content[:150] + ("..." if len(req.content) > 150 else ""),
            {"type": "NOTICE", "id": notice_id},
        )

    # Send email notification if urgent / requested
    if req.send_email:
        # Collect recipients based on audience
        email_query = {}
        if req.target_audience != TargetAudience.ALL:
            email_query["role"] = "STUDENT" if req.target_audience.value == "STUDENTS" else "FACULTY"
        recipients_cursor = db.users.find(email_query, {"email": 1}).limit(200)
        emails = [u["email"] async for u in recipients_cursor if u.get("email")]
        if emails:
            await email_service.send_email(
                to_emails=emails,
                subject=f"[Notice] {req.title}",
                html_content=f"<h3>{req.title}</h3><p>{req.content}</p>",
            )

    await audit_service.log_action(
        action="NOTICE_PUBLISHED",
        entity_type="NOTICE",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=notice_id,
        details={"title": req.title, "audience": doc["target_audience"]},
    )

    doc.pop("_id", None)
    return {"id": notice_id, **doc}


@router.put("/{notice_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def update_notice(notice_id: str, req: NoticeUpdate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    n = await db.notices.find_one({"_id": oid(notice_id)})
    if not n:
        raise HTTPException(status_code=404, detail="Notice not found.")
    if is_faculty(current_user) and n.get("published_by_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only edit notices you published.")
    update = {k: (v.value if hasattr(v, "value") else v) for k, v in req.model_dump().items() if v is not None}
    update["updated_at"] = datetime.now(timezone.utc)
    await db.notices.update_one({"_id": n["_id"]}, {"$set": update})
    n.update(update)
    n["id"] = str(n.pop("_id"))
    return n


@router.delete("/{notice_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.FACULTY]))])
async def delete_notice(notice_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    n = await db.notices.find_one({"_id": oid(notice_id)})
    if n and is_faculty(current_user) and n.get("published_by_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete notices you published.")
    res = await db.notices.delete_one({"_id": oid(notice_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notice not found.")

    return {"message": "Notice deleted successfully."}
