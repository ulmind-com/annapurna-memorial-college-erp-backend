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
        items.append({
            "id": str(m["_id"]),
            "exam_id": m.get("exam_id", "exam-1"),
            "exam_title": m.get("exam_title", ""),
            "student_id": m.get("student_id", ""),
            "roll_number": m.get("roll_number", ""),
            "registration_number": m.get("registration_number"),
            "student_name": m.get("student_name", ""),
            "course_code": m.get("course_code", ""),
            "course_name": m.get("course_name", m.get("course_code", "")),
            "semester": m.get("semester", 1),
            "academic_session": m.get("academic_session", "2024-2026"),
            "subject_scores": m.get("subject_scores", []),
            "total_marks_obtained": m.get("total_marks_obtained", 0.0),
            "grand_max_marks": m.get("grand_max_marks", 0.0),
            "overall_percentage": m.get("overall_percentage", 0.0),
            "sgpa": m.get("sgpa", 0.0),
            "result_status": m.get("result_status", "PASS"),
            "status": m.get("status", "DRAFT"),
            "qr_code_hash": m.get("qr_code_hash", ""),
            "faculty_remarks": m.get("faculty_remarks"),
            "principal_remarks": m.get("principal_remarks"),
            "certified_at": m.get("certified_at"),
            "published_at": m.get("published_at"),
            "created_at": m.get("created_at"),
        })
    return items


@router.post("/marksheets")
async def save_or_update_marksheet(
    data: dict,
    current_user: dict = Depends(require_roles([UserRole.FACULTY, UserRole.ADMIN, UserRole.SUPER_ADMIN])),
):
    db = await get_db()
    student_id = data.get("student_id", "st-unknown")
    roll_number = data.get("roll_number", "AMC-000")
    semester = data.get("semester", 1)
    marksheet_id = data.get("id")

    query = {}
    if marksheet_id and ObjectId.is_valid(marksheet_id):
        query = {"_id": ObjectId(marksheet_id)}
    elif marksheet_id and not marksheet_id.startswith("ms-"):
        query = {"id": marksheet_id}
    else:
        query = {"$or": [{"student_id": student_id, "semester": semester}, {"roll_number": roll_number, "semester": semester}]}

    existing = await db.marksheets.find_one(query)

    # Compute SGPA and totals if scores provided
    subject_scores = data.get("subject_scores", [])
    total_obtained = sum(float(s.get("total_obtained", 0)) for s in subject_scores)
    grand_max = sum(float(s.get("max_marks", 100)) for s in subject_scores) or 100.0
    overall_pct = round((total_obtained / grand_max) * 100, 2) if grand_max > 0 else 0.0

    total_credits = sum(float(s.get("credits", 4)) for s in subject_scores) or 1.0
    weighted_gp = sum(float(s.get("credits", 4)) * float(s.get("grade_point", 8.0)) for s in subject_scores)
    sgpa = round(weighted_gp / total_credits, 2) if total_credits > 0 else 8.0

    qr_hash = data.get("qr_code_hash") or f"AMCE-{roll_number}-{semester}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    doc = {
        "exam_id": data.get("exam_id", "exam-1"),
        "exam_title": data.get("exam_title", "Semester Examination"),
        "student_id": student_id,
        "roll_number": roll_number,
        "registration_number": data.get("registration_number", "Pending"),
        "student_name": data.get("student_name", "Student Trainee"),
        "course_code": data.get("course_code", "BED"),
        "course_name": data.get("course_name", "Bachelor of Education"),
        "semester": semester,
        "academic_session": data.get("academic_session", "2024-2026"),
        "subject_scores": subject_scores,
        "total_marks_obtained": total_obtained,
        "grand_max_marks": grand_max,
        "overall_percentage": overall_pct,
        "sgpa": sgpa,
        "result_status": data.get("result_status", "PASS" if overall_pct >= 40 else "FAIL"),
        "status": data.get("status", "SUBMITTED_BY_FACULTY"),
        "qr_code_hash": qr_hash,
        "faculty_remarks": data.get("faculty_remarks", "Evaluated and verified."),
        "updated_at": datetime.now(timezone.utc),
    }

    if existing:
        await db.marksheets.update_one({"_id": existing["_id"]}, {"$set": doc})
        doc_id = str(existing["_id"])
    else:
        doc["created_at"] = datetime.now(timezone.utc)
        res = await db.marksheets.insert_one(doc)
        doc_id = str(res.inserted_id)

    doc.pop("_id", None)
    return {"id": doc_id, **doc}


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
    items = []
    async for m in cursor:
        items.append({
            "id": str(m["_id"]),
            "exam_id": m["exam_id"],
            "exam_title": m.get("exam_title", ""),
            "student_id": m["student_id"],
            "roll_number": m["roll_number"],
            "registration_number": m.get("registration_number"),
            "student_name": m["student_name"],
            "course_code": m["course_code"],
            "course_name": m.get("course_name", m["course_code"]),
            "semester": m["semester"],
            "academic_session": m["academic_session"],
            "subject_scores": m.get("subject_scores", []),
            "total_marks_obtained": m.get("total_marks_obtained", 0.0),
            "grand_max_marks": m.get("grand_max_marks", 0.0),
            "overall_percentage": m.get("overall_percentage", 0.0),
            "sgpa": m.get("sgpa", 0.0),
            "cgpa": m.get("cgpa", 0.0),
            "letter_grade": m.get("letter_grade", "P"),
            "result_status": m.get("result_status", "PASS"),
            "status": m.get("status", "DRAFT"),
            "qr_code_hash": m.get("qr_code_hash", ""),
            "faculty_submitted_by": m.get("faculty_submitted_by"),
            "faculty_submitted_at": m.get("faculty_submitted_at"),
            "department_verified_by": m.get("department_verified_by"),
            "department_verified_at": m.get("department_verified_at"),
            "admin_approved_by": m.get("admin_approved_by"),
            "admin_approved_at": m.get("admin_approved_at"),
            "published_at": m.get("published_at"),
            "rejection_reason": m.get("rejection_reason"),
            "audit_trail": m.get("audit_trail", []),
            "created_at": m.get("created_at"),
            "updated_at": m.get("updated_at"),
        })

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
                "performed_by_name": current_user.get("name", "Faculty"),
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
        update_fields["faculty_submitted_by"] = current_user.get("name", "Faculty")
        update_fields["faculty_submitted_at"] = now
    elif next_status == MarksheetStatus.DEPARTMENT_VERIFIED:
        update_fields["department_verified_by"] = current_user.get("name", "Academic Coordinator")
        update_fields["department_verified_at"] = now
    elif next_status == MarksheetStatus.ADMIN_APPROVED:
        update_fields["admin_approved_by"] = current_user.get("name", "Principal")
        update_fields["admin_approved_at"] = now
    elif next_status == MarksheetStatus.PUBLISHED:
        update_fields["published_at"] = now
    elif next_status == MarksheetStatus.REJECTED:
        update_fields["rejection_reason"] = action_data.remarks

    audit_entry = {
        "stage": next_status.value,
        "performed_by_id": current_user["id"],
        "performed_by_name": current_user.get("name", "User"),
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
        student = await db.students.find_one({"_id": ObjectId(ms["student_id"])})
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
    ms = await db.marksheets.find_one({"_id": ObjectId(marksheet_id)})
    if not ms:
        raise HTTPException(status_code=404, detail="Marksheet not found.")

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
    ms = await db.marksheets.find_one({"qr_code_hash": qr_hash.upper()})
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

    res = await db.marksheets.update_many(
        {
            "$or": [
                {"course_code": {"$regex": f"^{clean_code}$", "$options": "i"}},
                {"course_code": {"$regex": f"^{norm_code}$", "$options": "i"}},
            ],
            "semester": semester,
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

    return {
        "message": f"Results and certificates successfully published for {course_code} Semester {semester}.",
        "modified_count": res.modified_count,
    }
