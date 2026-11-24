from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.examination import (
    ExaminationCreate,
    ExaminationResponse,
    MarksheetCreate,
    MarksheetBulkInput,
    MarksheetWorkflowAction,
    MarksheetResponse,
    MarksheetStatus,
    AuditTrailEntry,
)
from annapurna_memorial_college_erp_backend.services.marksheet_service import marksheet_service
from annapurna_memorial_college_erp_backend.services.email_service import email_service
from annapurna_memorial_college_erp_backend.services.audit_service import audit_service

from annapurna_memorial_college_erp_backend.deps import (
    get_student_record, get_faculty_scope, classes_query, is_student, is_faculty, oid,
)
from annapurna_memorial_college_erp_backend.services.notification_service import notification_service


async def _notify_result(student_ids: list, db) -> None:
    ids = [i for i in student_ids if i]
    if not ids:
        return
    user_ids = [str(u["_id"]) async for u in db.users.find({"entity_id": {"$in": ids}}, {"_id": 1})]
    await notification_service.notify_users(
        db, user_ids, "Result Published", "Your semester marksheet is now available. Open the app to download it.",
        {"type": "RESULT"},
    )


router = APIRouter(prefix="/examinations", tags=["Examinations & Marksheet Pipeline"])


@router.get("")
async def list_examinations(
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    academic_session: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if course_code:
        query["course_code"] = course_code
    if semester:
        query["semester"] = semester
    if academic_session:
        query["academic_session"] = academic_session

    cursor = db.examinations.find(query).sort("created_at", -1)
    exams = []
    async for e in cursor:
        exams.append({
            "id": str(e["_id"]),
            "code": e["code"],
            "title": e["title"],
            "course_code": e["course_code"],
            "semester": e["semester"],
            "academic_session": e["academic_session"],
            "exam_type": e.get("exam_type", "SEMESTER_FINAL"),
            "start_date": e["start_date"],
            "end_date": e["end_date"],
            "is_active": e.get("is_active", True),
            "created_at": e.get("created_at"),
            "updated_at": e.get("updated_at"),
        })
    return exams


@router.post("", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def create_examination(req: ExaminationCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    existing = await db.examinations.find_one({"code": req.code})
    if existing:
        raise HTTPException(status_code=400, detail="Examination code already exists.")

    doc = req.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    res = await db.examinations.insert_one(doc)

    await audit_service.log_action(
        action="EXAM_CREATED",
        entity_type="EXAMINATION",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        entity_id=str(res.inserted_id),
        details={"code": req.code, "title": req.title},
    )

    doc.pop("_id", None)
    return {"id": str(res.inserted_id), **doc}


@router.get("/marksheets")
async def list_all_marksheets(
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    exam_id: Optional[str] = None,
    status: Optional[MarksheetStatus] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if course_code:
        query["course_code"] = course_code
    if semester:
        query["semester"] = semester
    if exam_id:
        query["exam_id"] = exam_id
    if status:
        query["status"] = status.value
    if search:
        query["$or"] = [
            {"student_name": {"$regex": search, "$options": "i"}},
            {"roll_number": {"$regex": search, "$options": "i"}},
            {"registration_number": {"$regex": search, "$options": "i"}},
        ]

    if is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        query.setdefault("$and", []).append(classes_query(scope["classes"]))

    # If student is viewing, only allow their own published marksheets
    if current_user.get("role") == UserRole.STUDENT.value:
        entity_id = current_user.get("entity_id")
        user_email = current_user.get("email")
        st_rec = None
        if entity_id:
            try:
                st_rec = await db.students.find_one({"_id": ObjectId(entity_id)})
            except Exception:
                st_rec = await db.students.find_one({"_id": entity_id})
        if not st_rec and user_email:
            st_rec = await db.students.find_one({"email": user_email})

        st_roll = st_rec.get("roll_number") if st_rec else None
        st_id = str(st_rec["_id"]) if st_rec else entity_id

        or_conds = []
        if st_id:
            or_conds.append({"student_id": st_id})
        if st_roll:
            or_conds.append({"roll_number": st_roll})

        if or_conds:
            query["$or"] = or_conds
        else:
            query["student_id"] = entity_id or "NONE"
        query["status"] = MarksheetStatus.PUBLISHED.value

    cursor = db.marksheets.find(query).skip((page - 1) * limit).limit(limit).sort("roll_number", 1)
    items = []
    async for m in cursor:
        items.append(_ms_out(m))
    return items


LOCKED_FOR_FACULTY = {
    MarksheetStatus.DEPARTMENT_VERIFIED.value,
    MarksheetStatus.ADMIN_APPROVED.value,
    MarksheetStatus.PUBLISHED.value,
    MarksheetStatus.SUBMITTED_BY_FACULTY.value,
}


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


async def _compute_scores(db, rows: list, course_code: str, semester: int) -> dict:
    """Validate and grade subject rows server-side. Rows use internal_marks / external_marks."""
    subjects = {s["code"]: s async for s in db.subjects.find({"course_code": course_code, "semester": semester})}
    processed, total_obt, grand_max, credits_sum, credit_points, any_fail = [], 0.0, 0.0, 0.0, 0.0, False
    for r in rows:
        code = (r.get("subject_code") or "").upper()
        sub = subjects.get(code)
        if not sub:
            raise HTTPException(status_code=400, detail=f"Subject '{code}' is not part of {course_code} Semester {semester}.")
        int_max = _num(sub.get("practical_marks", 30))
        ext_max = _num(sub.get("theory_marks", 70))
        internal = _num(r.get("internal_marks", r.get("practical_obtained")))
        external = _num(r.get("external_marks", r.get("theory_obtained")))
        if internal < 0 or internal > int_max:
            raise HTTPException(status_code=400, detail=f"{code}: internal marks must be 0-{int_max:g}.")
        if external < 0 or external > ext_max:
            raise HTTPException(status_code=400, detail=f"{code}: external marks must be 0-{ext_max:g}.")
        tot, mx = internal + external, int_max + ext_max
        pct = (tot / mx * 100.0) if mx else 0.0
        gp, letter = marksheet_service.calculate_grade(pct)
        if tot < _num(sub.get("pass_marks", 40)):
            letter, gp = "F", 0.0
        any_fail = any_fail or letter == "F"
        credits = _num(sub.get("credits", 4))
        total_obt += tot
        grand_max += mx
        credits_sum += credits
        credit_points += credits * gp
        processed.append({
            "subject_code": code,
            "subject_title": sub.get("title", code),
            "credits": credits,
            "internal_marks": internal,
            "external_marks": external,
            "internal_max": int_max,
            "external_max": ext_max,
            "practical_obtained": internal,
            "theory_obtained": external,
            "max_practical": int_max,
            "max_theory": ext_max,
            "total_obtained": tot,
            "total_maximum": mx,
            "max_marks": mx,
            "percentage": round(pct, 2),
            "grade_point": gp,
            "letter_grade": letter,
            "entered_by": r.get("entered_by"),
        })
    overall = round(total_obt / grand_max * 100.0, 2) if grand_max else 0.0
    sgpa = round(credit_points / credits_sum, 2) if credits_sum else 0.0
    _, overall_letter = marksheet_service.calculate_grade(overall)
    return {
        "subject_scores": processed,
        "total_marks_obtained": total_obt,
        "grand_max_marks": grand_max,
        "total_marks_maximum": grand_max,
        "overall_percentage": overall,
        "percentage": overall,
        "sgpa": sgpa,
        "cgpa": sgpa,
        "letter_grade": "F" if any_fail else overall_letter,
        "result_status": marksheet_service.determine_result_status(overall, any_fail),
    }


async def _merge_rows(db, current_user: dict, existing_rows: list, incoming: list) -> list:
    """Teachers may only change rows of subjects they teach; other rows are kept as-is."""
    if not is_faculty(current_user):
        for r in incoming:
            r.setdefault("entered_by", current_user.get("full_name"))
        return incoming
    scope = await get_faculty_scope(db, current_user)
    mine = {s["code"].upper() for s in scope["subjects"]}
    merged = {(r.get("subject_code") or "").upper(): r for r in existing_rows}
    for r in incoming:
        code = (r.get("subject_code") or "").upper()
        if code in mine:
            r["entered_by"] = current_user.get("full_name")
            merged[code] = r
    return list(merged.values())


async def _upsert_marksheet(db, current_user: dict, data: dict, existing: Optional[dict]) -> dict:
    student = await db.students.find_one({"_id": oid(data.get("student_id") or (existing or {}).get("student_id", ""))})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    course_code = student.get("course_code")
    semester = int(data.get("semester") or (existing or {}).get("semester") or student.get("semester", 1))

    if is_faculty(current_user):
        scope = await get_faculty_scope(db, current_user)
        if (course_code, semester) not in scope["classes"]:
            raise HTTPException(status_code=403, detail="This student is not in your assigned classes.")
        if existing and existing.get("status") in LOCKED_FOR_FACULTY:
            raise HTTPException(status_code=400, detail=f"Marksheet is {existing.get('status')} and locked for editing.")

    rows = await _merge_rows(db, current_user, (existing or {}).get("subject_scores", []), data.get("subject_scores") or data.get("scores") or [])
    if not rows:
        raise HTTPException(status_code=400, detail="Enter marks for at least one subject.")
    computed = await _compute_scores(db, rows, course_code, semester)

    exam_id = data.get("exam_id") or (existing or {}).get("exam_id") or ""
    exam = await db.examinations.find_one({"_id": ObjectId(exam_id)}) if ObjectId.is_valid(exam_id) else None
    course = await db.courses.find_one({"code": course_code})
    now = datetime.now(timezone.utc)

    if is_faculty(current_user):
        new_status = MarksheetStatus.SUBMITTED_BY_FACULTY.value if data.get("submit") else MarksheetStatus.DRAFT.value
    elif existing and existing.get("status") not in (MarksheetStatus.DRAFT.value, MarksheetStatus.REJECTED.value):
        new_status = existing["status"]
    else:
        # Marks entered directly by the Principal/Admin are approved and ready to publish
        new_status = MarksheetStatus.ADMIN_APPROVED.value

    doc = {
        "exam_id": exam_id,
        "exam_title": exam["title"] if exam else f"{(course or {}).get('name', course_code)} Semester {semester} Examination",
        "student_id": str(student["_id"]),
        "roll_number": student.get("roll_number"),
        "registration_number": student.get("registration_number"),
        "student_name": student.get("full_name"),
        "course_code": course_code,
        "course_name": (course or {}).get("name", course_code),
        "semester": semester,
        "academic_session": student.get("academic_session", ""),
        **computed,
        "status": new_status,
        "faculty_remarks": data.get("remarks") or data.get("faculty_remarks") or (existing or {}).get("faculty_remarks"),
        "remarks": data.get("remarks") or (existing or {}).get("remarks"),
        "updated_at": now,
    }
    if new_status == MarksheetStatus.SUBMITTED_BY_FACULTY.value:
        doc["faculty_submitted_by"] = current_user.get("full_name")
        doc["faculty_submitted_at"] = now
    if new_status == MarksheetStatus.ADMIN_APPROVED.value and not (existing or {}).get("admin_approved_by"):
        doc["admin_approved_by"] = current_user.get("full_name")
        doc["admin_approved_at"] = now
    audit = {
        "stage": new_status,
        "performed_by_id": current_user["id"],
        "performed_by_name": current_user.get("full_name"),
        "performed_by_role": current_user.get("role"),
        "timestamp": now,
        "action": "SCORES_SAVED",
        "remarks": doc["remarks"],
    }
    if existing:
        await db.marksheets.update_one({"_id": existing["_id"]}, {"$set": doc, "$push": {"audit_trail": audit}})
        ms_id = str(existing["_id"])
    else:
        doc["qr_code_hash"] = marksheet_service.generate_verification_hash(doc["student_id"], f"{exam_id}:{semester}", doc["sgpa"])
        doc["created_at"] = now
        doc["audit_trail"] = [audit]
        res = await db.marksheets.insert_one(doc)
        ms_id = str(res.inserted_id)

    await audit_service.log_action(
        action="MARKS_SAVED", entity_type="MARKSHEET", user_id=current_user["id"],
        user_email=current_user["email"], user_role=current_user["role"], entity_id=ms_id,
        details={"student_roll": doc["roll_number"], "semester": semester, "status": new_status},
    )
    saved = await db.marksheets.find_one({"_id": ObjectId(ms_id)})
    return _ms_out(saved)


def _ms_out(m: dict) -> dict:
    out = {k: v for k, v in m.items() if k != "_id"}
    out["id"] = str(m["_id"])
    return out


@router.post("/marksheets")
async def save_or_update_marksheet(
    data: dict,
    current_user: dict = Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN])),
):
    db = await get_db()
    existing = None
    if data.get("id") and ObjectId.is_valid(data["id"]):
        existing = await db.marksheets.find_one({"_id": ObjectId(data["id"])})
    if not existing and data.get("student_id"):
        existing = await db.marksheets.find_one({
            "student_id": data["student_id"], "semester": int(data.get("semester") or 0),
        })
    return await _upsert_marksheet(db, current_user, data, existing)


@router.put("/marksheets/{marksheet_id}")
async def update_marksheet_scores(
    marksheet_id: str,
    data: dict,
    current_user: dict = Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN])),
):
    db = await get_db()
    existing = await db.marksheets.find_one({"_id": oid(marksheet_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Marksheet not found.")
    return await _upsert_marksheet(db, current_user, data, existing)


@router.get("/marksheets/detail/{marksheet_id}")
async def get_marksheet_detail(marksheet_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    ms = await db.marksheets.find_one({"_id": ObjectId(marksheet_id)})
    if not ms:
        raise HTTPException(status_code=404, detail="Marksheet not found.")

    return {
        "id": str(ms["_id"]),
        **{k: v for k, v in ms.items() if k != "_id"},
    }


@router.get("/{exam_id}/marksheets")
async def list_exam_marksheets(
    exam_id: str,
    status: Optional[MarksheetStatus] = None,
    student_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {"exam_id": exam_id}
    if status:
        query["status"] = status.value
    if student_id:
        query["student_id"] = student_id

    # If student is viewing, only allow published marksheet for themself
    if current_user.get("role") == UserRole.STUDENT.value:
        entity_id = current_user.get("entity_id")
        user_email = current_user.get("email")
        st_rec = None
        if entity_id:
            try:
                st_rec = await db.students.find_one({"_id": ObjectId(entity_id)})
            except Exception:
                st_rec = await db.students.find_one({"_id": entity_id})
        if not st_rec and user_email:
            st_rec = await db.students.find_one({"email": user_email})

        st_roll = st_rec.get("roll_number") if st_rec else None
        st_id = str(st_rec["_id"]) if st_rec else entity_id

        or_conds = []
        if st_id:
            or_conds.append({"student_id": st_id})
        if st_roll:
            or_conds.append({"roll_number": st_roll})

        if or_conds:
            query["$or"] = or_conds
        else:
            query["student_id"] = entity_id or "NONE"
        query["status"] = MarksheetStatus.PUBLISHED.value

    cursor = db.marksheets.find(query).sort("roll_number", 1)
    items = [_ms_out(m) async for m in cursor]
    return items


@router.post("/{exam_id}/marksheets/entry", dependencies=[Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def enter_student_marks(
    exam_id: str,
    req: MarksheetCreate,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    exam = await db.examinations.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        raise HTTPException(status_code=404, detail="Examination not found.")

    student = await db.students.find_one({"_id": ObjectId(req.student_id)})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    # Process subject scores through marksheet service
    (
        processed_scores,
        total_obtained,
        grand_max,
        percentage,
        sgpa,
        result_status,
    ) = marksheet_service.process_subject_scores(req.subject_scores)

    verification_hash = marksheet_service.generate_verification_hash(
        student_id=req.student_id,
        exam_id=exam_id,
        sgpa=sgpa,
    )

    marksheet_doc = {
        "exam_id": exam_id,
        "exam_title": exam["title"],
        "student_id": req.student_id,
        "roll_number": student["roll_number"],
        "registration_number": student.get("registration_number"),
        "student_name": student["full_name"],
        "course_code": exam["course_code"],
        "course_name": student.get("course_name", exam["course_code"]),
        "semester": exam["semester"],
        "academic_session": exam["academic_session"],
        "subject_scores": [s.model_dump() for s in processed_scores],
        "total_marks_obtained": total_obtained,
        "grand_max_marks": grand_max,
        "overall_percentage": percentage,
        "sgpa": sgpa,
        "cgpa": sgpa,  # initially equal to SGPA
        "letter_grade": processed_scores[0].letter_grade if processed_scores else "P",
        "result_status": result_status,
        "status": MarksheetStatus.DRAFT.value,
        "qr_code_hash": verification_hash,
        "audit_trail": [
            {
                "stage": "DRAFT_CREATED",
                "performed_by_id": current_user["id"],
                "performed_by_name": current_user.get("full_name"),
                "performed_by_role": current_user.get("role", "FACULTY"),
                "timestamp": datetime.now(timezone.utc),
                "action": "SCORES_ENTERED",
                "remarks": "Initial marks entered and computed.",
            }
        ],
        "created_at": datetime.now(timezone.utc),
    }

    # Upsert by exam_id and student_id
    res = await db.marksheets.update_one(
        {"exam_id": exam_id, "student_id": req.student_id},
        {"$set": marksheet_doc},
        upsert=True,
    )

    await audit_service.log_action(
        action="MARKS_ENTERED",
        entity_type="MARKSHEET",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        details={"exam_id": exam_id, "student_roll": student["roll_number"], "sgpa": sgpa},
    )

    return {"message": "Marks recorded and grades computed successfully.", "sgpa": sgpa, "percentage": percentage}


@router.post("/marksheets/{marksheet_id}/action")
async def execute_workflow_action(
    marksheet_id: str,
    action_data: MarksheetWorkflowAction,
    current_user: dict = Depends(get_current_user),
):
    """
    Core Pipeline Transitions:
    DRAFT -> SUBMITTED_BY_FACULTY -> DEPARTMENT_VERIFIED -> ADMIN_APPROVED -> PUBLISHED
    or REJECTED
    """
    db = await get_db()
    ms = await db.marksheets.find_one({"_id": ObjectId(marksheet_id)})
    if not ms:
        raise HTTPException(status_code=404, detail="Marksheet not found.")

    current_status = MarksheetStatus(ms.get("status", MarksheetStatus.DRAFT.value))
    user_role = current_user.get("role", "FACULTY")
    if is_student(current_user):
        raise HTTPException(status_code=403, detail="Access denied.")
    if is_faculty(current_user):
        if action_data.action.upper() != "SUBMIT":
            raise HTTPException(status_code=403, detail="Teachers can only submit marksheets for review.")
        scope = await get_faculty_scope(db, current_user)
        if (ms.get("course_code"), ms.get("semester")) not in scope["classes"]:
            raise HTTPException(status_code=403, detail="This student is not in your assigned classes.")

    # Validate transition state machine
    next_status = marksheet_service.validate_transition(
        current_status=current_status,
        action=action_data.action,
        user_role=user_role,
        remarks=action_data.remarks or "",
    )

    now = datetime.now(timezone.utc)
    update_fields = {
        "status": next_status.value,
        "updated_at": now,
    }

    if next_status == MarksheetStatus.SUBMITTED_BY_FACULTY:
        update_fields["faculty_submitted_by"] = current_user.get("full_name")
        update_fields["faculty_submitted_at"] = now
    elif next_status == MarksheetStatus.DEPARTMENT_VERIFIED:
        update_fields["department_verified_by"] = current_user.get("full_name")
        update_fields["department_verified_at"] = now
    elif next_status == MarksheetStatus.ADMIN_APPROVED:
        update_fields["admin_approved_by"] = current_user.get("full_name")
        update_fields["admin_approved_at"] = now
    elif next_status == MarksheetStatus.PUBLISHED:
        update_fields["published_at"] = now
    elif next_status == MarksheetStatus.REJECTED:
        update_fields["rejection_reason"] = action_data.remarks

    audit_entry = {
        "stage": next_status.value,
        "performed_by_id": current_user["id"],
        "performed_by_name": current_user.get("full_name"),
        "performed_by_role": user_role,
        "timestamp": now,
        "action": action_data.action.upper(),
        "remarks": action_data.remarks,
    }

    await db.marksheets.update_one(
        {"_id": ObjectId(marksheet_id)},
        {"$set": update_fields, "$push": {"audit_trail": audit_entry}},
    )

    # If published, trigger notification dispatch to student
    if next_status == MarksheetStatus.PUBLISHED:
        await _notify_result([ms["student_id"]], db)
        student = await db.students.find_one({"_id": ObjectId(ms["student_id"])}) if ObjectId.is_valid(ms.get("student_id", "")) else None
        if student and student.get("email"):
            await email_service.send_marksheet_publication_notice(
                to_email=student["email"],
                student_name=student["full_name"],
                exam_title=ms.get("exam_title", "Semester Examination"),
            )

    await audit_service.log_action(
        action=f"MARKSHEET_{action_data.action.upper()}",
        entity_type="MARKSHEET",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=user_role,
        entity_id=marksheet_id,
        details={"previous_status": current_status.value, "new_status": next_status.value},
    )

    return {
        "message": f"Marksheet transitioned to {next_status.value}",
        "status": next_status.value,
    }


@router.get("/marksheets/{marksheet_id}/pdf")
async def download_marksheet_pdf(
    marksheet_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    ms = await db.marksheets.find_one({"_id": oid(marksheet_id)})
    if not ms:
        raise HTTPException(status_code=404, detail="Marksheet not found.")
    if is_student(current_user):
        st = await get_student_record(db, current_user, required=True)
        if ms.get("student_id") != str(st["_id"]) or ms.get("status") != MarksheetStatus.PUBLISHED.value:
            raise HTTPException(status_code=403, detail="Marksheet is not available.")
    template = await db.app_settings.find_one({"key": "marksheet_template"})
    ms["_template"] = (template or {}).get("value", {})
    pdf_bytes = marksheet_service.generate_pdf(ms)
    filename = f"Marksheet_{ms.get('roll_number')}_{ms.get('semester')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/verify/{qr_hash}")
async def public_verify_marksheet(qr_hash: str):
    """
    Publicly accessible endpoint for third-party universities/employers to verify marksheets!
    """
    db = await get_db()
    ms = await db.marksheets.find_one({"qr_code_hash": qr_hash.strip().upper(), "status": MarksheetStatus.PUBLISHED.value})
    if not ms:
        raise HTTPException(status_code=404, detail="Invalid verification hash. Record not found.")

    return {
        "is_verified": True,
        "college": "Annapurna Memorial College & Sundarban Ashutosh B.Ed. College",
        "student_name": ms["student_name"],
        "roll_number": ms["roll_number"],
        "registration_number": ms.get("registration_number"),
        "course": ms.get("course_name", ms["course_code"]),
        "semester": ms["semester"],
        "session": ms["academic_session"],
        "sgpa": ms["sgpa"],
        "result_status": ms["result_status"],
        "status": ms["status"],
        "issued_date": ms.get("published_at") or ms.get("created_at"),
    }


@router.post("/publish-results", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN]))])
async def publish_course_results(
    course_code: str = Query(..., description="Course code to publish"),
    semester: int = Query(..., description="Semester to publish"),
    current_user: dict = Depends(get_current_user),
):
    """
    Publish all semester results and digital certificates for a given course & semester.
    Makes marksheets instantly visible to all enrolled trainees.
    """
    db = await get_db()
    now = datetime.now(timezone.utc)
    clean_code = course_code.strip()
    norm_code = clean_code.replace(".", "").upper()

    to_publish = [m["student_id"] async for m in db.marksheets.find({
        "course_code": norm_code, "semester": semester,
        "status": {"$in": [MarksheetStatus.SUBMITTED_BY_FACULTY.value, MarksheetStatus.DEPARTMENT_VERIFIED.value, MarksheetStatus.ADMIN_APPROVED.value]},
    }, {"student_id": 1})]
    res = await db.marksheets.update_many(
        {
            "$or": [
                {"course_code": {"$regex": f"^{clean_code}$", "$options": "i"}},
                {"course_code": {"$regex": f"^{norm_code}$", "$options": "i"}},
            ],
            "semester": semester,
            "status": {"$in": [
                MarksheetStatus.SUBMITTED_BY_FACULTY.value,
                MarksheetStatus.DEPARTMENT_VERIFIED.value,
                MarksheetStatus.ADMIN_APPROVED.value,
            ]},
        },
        {
            "$set": {
                "status": MarksheetStatus.PUBLISHED.value,
                "published_at": now,
                "certified_at": now,
            }
        }
    )

    await audit_service.log_action(
        action="EXAMINATION_RESULTS_PUBLISHED",
        entity_type="EXAMINATION",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        details={"course_code": course_code, "semester": semester, "published_count": res.modified_count},
    )

    await _notify_result(to_publish, db)
    if res.modified_count == 0:
        return {"message": "No submitted/approved marksheets to publish for this class. Draft and rejected marksheets are not published.", "modified_count": 0}
    return {
        "message": f"Results and certificates successfully published for {course_code} Semester {semester}.",
        "modified_count": res.modified_count,
    }
