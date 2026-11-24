"""Editable institution settings (college profile, marksheet template) stored in MongoDB."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import get_current_user, require_roles, UserRole

router = APIRouter(prefix="/settings", tags=["Institution Settings"])

import re

# college_profile, marksheet_template, certificate_template, and per-course overrides
# such as marksheet_template:BED / certificate_template:BTECH
KEY_RE = re.compile(r"^(college_profile|(marksheet|certificate)_template(:[A-Z0-9_]{1,20})?)$")


def _check_key(key: str) -> None:
    if not KEY_RE.match(key):
        raise HTTPException(status_code=404, detail="Unknown setting.")


@router.get("/{key}")
async def get_setting(key: str, current_user: dict = Depends(get_current_user)):
    _check_key(key)
    db = await get_db()
    doc = await db.app_settings.find_one({"key": key})
    return (doc or {}).get("value", {})


@router.put("/{key}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def put_setting(key: str, value: dict):
    _check_key(key)
    db = await get_db()
    await db.app_settings.update_one(
        {"key": key},
        {"$set": {"value": value, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return value
