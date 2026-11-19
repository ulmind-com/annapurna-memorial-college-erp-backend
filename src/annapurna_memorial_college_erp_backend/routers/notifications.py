from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.notification import (
    DeviceTokenRegisterRequest,
    PushNotificationSendRequest,
    NotificationStatusResponse,
)
from annapurna_memorial_college_erp_backend.services.notification_service import notification_service
from annapurna_memorial_college_erp_backend.services.audit_service import audit_service

router = APIRouter(prefix="/notifications", tags=["Mobile Push Notifications (FCM)"])


@router.post("/register-device")
async def register_device_token(
    req: DeviceTokenRegisterRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Mobile Application (Android/iOS) FCM Device Token Registration.
    Called upon mobile app launch or user sign-in to bind the device's FCM Push Token to the authenticated ERP user.
    """
    db = await get_db()
    token_doc = {
        "user_id": current_user["id"],
        "user_email": current_user.get("email"),
        "role": current_user.get("role"),
        "fcm_token": req.fcm_token.strip(),
        "platform": req.platform.lower(),
        "device_id": req.device_id,
        "device_model": req.device_model,
        "app_version": req.app_version,
        "updated_at": datetime.now(timezone.utc),
    }

    # Upsert by fcm_token to avoid duplicates if user re-registers or switches devices
    await db.device_tokens.update_one(
        {"fcm_token": req.fcm_token.strip()},
        {"$set": token_doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    return {
        "success": True,
        "message": "FCM device registration token recorded successfully.",
        "user_id": current_user["id"],
        "platform": req.platform,
    }


@router.delete("/unregister-device")
async def unregister_device_token(
    fcm_token: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Called when a user logs out from the mobile app to deregister the push token.
    """
    db = await get_db()
    res = await db.device_tokens.delete_one({
        "fcm_token": fcm_token.strip(),
        "user_id": current_user["id"],
    })
    return {
        "success": res.deleted_count > 0,
        "message": "Device token deregistered." if res.deleted_count > 0 else "Token not found.",
    }


@router.get("/status")
async def get_notification_system_status(
    current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN])),
):
    """
    System status of Firebase Cloud Messaging service and active registered mobile devices.
    """
    db = await get_db()
    total_devices = await db.device_tokens.count_documents({})
    android_devices = await db.device_tokens.count_documents({"platform": "android"})
    ios_devices = await db.device_tokens.count_documents({"platform": "ios"})

    is_firebase_live = notification_service.firebase_app is not None

    return {
        "firebase_admin_initialized": is_firebase_live,
        "mode": "PRODUCTION_FCM" if is_firebase_live else "FALLBACK_LOGGING",
        "registered_devices_total": total_devices,
        "platform_breakdown": {
            "android": android_devices,
            "ios": ios_devices,
            "other": total_devices - (android_devices + ios_devices),
        },
        "supported_topics": ["all", "students", "faculty", "announcements", "examinations"],
    }


@router.post("/broadcast", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def broadcast_push_notification(
    req: PushNotificationSendRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Super Admin / Admin push broadcast endpoint.
    Sends FCM push messages to a topic or direct user devices.
    """
    db = await get_db()
    tokens: List[str] = []

    if req.user_ids:
        cursor = db.device_tokens.find({"user_id": {"$in": req.user_ids}}, {"fcm_token": 1})
        async for doc in cursor:
            tokens.append(doc["fcm_token"])

    success = await notification_service.send_push_notification(
        title=req.title,
        body=req.body,
        topic=req.topic,
        tokens=tokens if tokens else None,
        data=req.data or {},
    )

    await audit_service.log_action(
        action="PUSH_NOTIFICATION_SENT",
        entity_type="NOTIFICATION",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        details={"title": req.title, "topic": req.topic, "recipient_count": len(tokens)},
    )

    return NotificationStatusResponse(
        success=success,
        message=f"Notification dispatched successfully to {req.topic or f'{len(tokens)} devices'}.",
        target_count=len(tokens) if tokens else 1,
    )
