"""Email validation shared by student/faculty create, update and the check-email API."""
import difflib
from typing import Optional
from bson import ObjectId
from email_validator import validate_email, EmailNotValidError
from fastapi import HTTPException

COMMON_PROVIDERS = [
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.in", "yahoo.co.in", "outlook.com",
    "hotmail.com", "live.com", "icloud.com", "rediffmail.com", "protonmail.com", "aol.com", "zoho.com",
]


class EmailProblem(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def check_email_format(email: str, check_dns: bool = True) -> str:
    """Return the normalized email or raise EmailProblem with a user-facing message."""
    raw = (email or "").strip().lower()
    if not raw:
        raise EmailProblem("Email address is required.")
    try:
        normalized = validate_email(raw, check_deliverability=check_dns).normalized.lower()
    except EmailNotValidError as e:
        raise EmailProblem(f"Invalid email address: {e}")

    domain = normalized.rsplit("@", 1)[1]
    if domain not in COMMON_PROVIDERS:
        close = difflib.get_close_matches(domain, COMMON_PROVIDERS, n=1, cutoff=0.8)
        if close:
            local = normalized.rsplit("@", 1)[0]
            raise EmailProblem(f"'{domain}' looks like a typo. Did you mean {local}@{close[0]}?")
    return normalized


async def find_email_owner(db, email: str, exclude_entity_id: Optional[str] = None) -> Optional[str]:
    """Describe who already uses this email (faculty, student or any login account), else None."""
    exclude_oid = ObjectId(exclude_entity_id) if exclude_entity_id and ObjectId.is_valid(exclude_entity_id) else None

    fac = await db.faculty.find_one({"email": email})
    if fac and fac["_id"] != exclude_oid:
        return f"faculty member '{fac.get('full_name')}' (Employee ID: {fac.get('employee_id')})"
    st = await db.students.find_one({"email": email})
    if st and st["_id"] != exclude_oid:
        return f"student '{st.get('full_name')}' (Roll: {st.get('roll_number')})"
    user = await db.users.find_one({"email": email})
    if user and (not exclude_entity_id or user.get("entity_id") != exclude_entity_id):
        return f"an existing {user.get('role', 'user').replace('_', ' ').lower()} login account"
    return None


async def validate_new_email(db, email: str, exclude_entity_id: Optional[str] = None) -> str:
    """Format + typo + DNS check and uniqueness across faculty, students and users. Raises HTTP 400."""
    try:
        normalized = check_email_format(email)
    except EmailProblem as e:
        raise HTTPException(status_code=400, detail=e.message)
    owner = await find_email_owner(db, normalized, exclude_entity_id)
    if owner:
        raise HTTPException(
            status_code=400,
            detail=f"This email is already used by {owner}. Please use another email address.",
        )
    return normalized
