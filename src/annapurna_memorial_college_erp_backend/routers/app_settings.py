"""Editable institution settings (college profile, marksheet template) stored in MongoDB."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import get_current_user, require_roles, UserRole

router = APIRouter(prefix="/settings", tags=["Institution Settings"])

ALLOWED_KEYS = {"college_profile", "marksheet_template"}


@router.get("/{key}")
async def get_setting(key: str, current_user: dict = Depends(get_current_user)):
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=404, detail="Unknown setting.")
    db = await get_db()
    doc = await db.app_settings.find_one({"key": key})
    return (doc or {}).get("value", {})


@router.put("/{key}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def put_setting(key: str, value: dict):
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=404, detail="Unknown setting.")
    db = await get_db()
    await db.app_settings.update_one(
        {"key": key},
        {"$set": {"value": value, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return value
