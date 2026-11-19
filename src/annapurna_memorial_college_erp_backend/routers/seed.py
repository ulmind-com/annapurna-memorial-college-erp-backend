from fastapi import APIRouter, Depends
from annapurna_memorial_college_erp_backend.security import require_roles, UserRole
from annapurna_memorial_college_erp_backend.seed import seed_all

router = APIRouter(prefix="/seed", tags=["Seed & Bootstrap Data"])


@router.post("", dependencies=[Depends(require_roles([UserRole.SUPER_ADMIN]))])
async def trigger_database_seed(force: bool = False):
    await seed_all(force=force)
    return {"message": "Database successfully seeded with realistic college records."}
