from datetime import datetime, timezone
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class DeviceTokenRegisterRequest(BaseModel):
    fcm_token: str = Field(..., description="Firebase Cloud Messaging Device Registration Token")
    platform: str = Field(default="android", description="Device platform (android, ios, web)")
    device_id: Optional[str] = Field(default=None, description="Unique client hardware/instance ID")
    device_model: Optional[str] = Field(default=None, description="Hardware model, e.g. Samsung Galaxy Tab S9")
    app_version: Optional[str] = Field(default=None, description="Android App version string")


class PushNotificationSendRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    body: str = Field(..., min_length=2, max_length=500)
    topic: Optional[str] = Field(default=None, description="FCM topic e.g. all, students, faculty")
    user_ids: Optional[List[str]] = Field(default=None, description="Direct recipient user IDs")
    data: Optional[Dict[str, str]] = Field(default_factory=dict, description="Custom payload key-values")


class NotificationStatusResponse(BaseModel):
    success: bool
    message: str
    target_count: int = 0
