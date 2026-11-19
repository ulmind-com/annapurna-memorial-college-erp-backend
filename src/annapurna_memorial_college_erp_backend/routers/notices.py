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

router = APIRouter(prefix="/notices", tags=["Notices & Circulars"])


@router.get("")
async def list_notices(
    category: Optional[NoticeCategory] = None,
    target_audience: Optional[TargetAudience] = None,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if category:
        query["category"] = category.value

    user_role = current_user.get("role", "STUDENT")
    if target_audience:
        query["target_audience"] = target_audience.value
    elif user_role == UserRole.STUDENT.value:
        query["target_audience"] = {"$in": ["ALL", "STUDENTS"]}
    elif user_role == UserRole.FACULTY.value:
        query["target_audience"] = {"$in": ["ALL", "FACULTY"]}

    cursor = db.notices.find(query).sort([("is_pinned", -1), ("created_at", -1)])
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
    doc["published_by_name"] = current_user.get("name", "College Office")
    doc["views_count"] = 0
    doc["created_at"] = datetime.now(timezone.utc)

    res = await db.notices.insert_one(doc)
    notice_id = str(res.inserted_id)

    # Broadcast push notification if requested
    if req.send_push:
        await notification_service.send_push_notification(
            title=f"Circular: {req.title}",
            body=req.content[:150] + ("..." if len(req.content) > 150 else ""),
            topic=req.target_audience.value.lower(),
        )

    # Send email notification if urgent / requested
    if req.send_email:
        # Collect recipients based on audience
        email_query = {}
        if req.target_audience != TargetAudience.ALL:
            email_query["role"] = req.target_audience.value[:-1]  # STUDENTS -> STUDENT
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

    return {"id": notice_id, **doc}


@router.delete("/{notice_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def delete_notice(notice_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    res = await db.notices.delete_one({"_id": ObjectId(notice_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notice not found.")

    return {"message": "Notice deleted successfully."}
