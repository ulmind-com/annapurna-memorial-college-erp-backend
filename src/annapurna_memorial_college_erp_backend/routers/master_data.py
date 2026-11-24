"""Admin-managed dropdown values (departments, designations, qualifications, specializations)."""
import re
from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import get_current_user, require_roles, UserRole
from annapurna_memorial_college_erp_backend.deps import oid

router = APIRouter(prefix="/master-data", tags=["Master Data"])

Category = Literal["DEPARTMENT", "DESIGNATION", "QUALIFICATION", "SPECIALIZATION"]
# Faculty field each category maps to (used to block deleting values that are in use)
FACULTY_FIELD = {
    "DEPARTMENT": "department",
    "DESIGNATION": "designation",
    "QUALIFICATION": "qualification",
    "SPECIALIZATION": "specialization",
}


class MasterItemIn(BaseModel):
    category: Category
    name: str


class MasterItemUpdate(BaseModel):
    name: str


def _out(d: dict) -> dict:
    return {"id": str(d["_id"]), "category": d["category"], "name": d["name"], "created_at": d.get("created_at")}


async def _ensure_unique(db, category: str, name: str, exclude=None):
    q = {"category": category, "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    if exclude:
        q["_id"] = {"$ne": exclude}
    if await db.master_data.find_one(q):
        raise HTTPException(status_code=400, detail=f"'{name}' already exists in {category.lower()} list.")


@router.get("")
async def list_master_data(category: Optional[Category] = None, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    q = {"category": category} if category else {}
    return [_out(d) async for d in db.master_data.find(q).sort([("category", 1), ("name", 1)])]


@router.post("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_master_item(req: MasterItemIn):
    db = await get_db()
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    await _ensure_unique(db, req.category, name)
    doc = {"category": req.category, "name": name, "created_at": datetime.now(timezone.utc)}
    res = await db.master_data.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _out(doc)


@router.put("/{item_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def rename_master_item(item_id: str, req: MasterItemUpdate):
    db = await get_db()
    item = await db.master_data.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    await _ensure_unique(db, item["category"], name, exclude=item["_id"])
    await db.master_data.update_one({"_id": item["_id"]}, {"$set": {"name": name}})
    # Keep faculty records consistent with the renamed value
    field = FACULTY_FIELD[item["category"]]
    await db.faculty.update_many({field: item["name"]}, {"$set": {field: name}})
    item["name"] = name
    return _out(item)


@router.delete("/{item_id}", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def delete_master_item(item_id: str):
    db = await get_db()
    item = await db.master_data.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")
    in_use = await db.faculty.count_documents({FACULTY_FIELD[item["category"]]: item["name"]})
    if in_use:
        raise HTTPException(status_code=400, detail=f"'{item['name']}' is used by {in_use} faculty member(s). Change them first.")
    await db.master_data.delete_one({"_id": item["_id"]})
    return {"message": "Deleted."}
