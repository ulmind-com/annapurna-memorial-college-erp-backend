import asyncio
import logging
from datetime import datetime, timezone, timedelta
from annapurna_memorial_college_erp_backend.config import settings
from annapurna_memorial_college_erp_backend.database import DatabaseManager, get_db
from annapurna_memorial_college_erp_backend.security import hash_password, UserRole
from annapurna_memorial_college_erp_backend.schemas.examination import MarksheetStatus
from annapurna_memorial_college_erp_backend.services.marksheet_service import marksheet_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("erp.seed")


async def seed_all(force: bool = False):
    db = await get_db()
    logger.info("Initializing database seeding for Annapurna Memorial College ERP...")

    if force:
        logger.info("Force flag detected. Purging previous ERP data...")
        await db.users.delete_many({})
        await db.students.delete_many({})
        await db.faculty.delete_many({})
        await db.courses.delete_many({})
        await db.subjects.delete_many({})
        await db.academic_sessions.delete_many({})
        await db.attendance.delete_many({})
        await db.examinations.delete_many({})
        await db.marksheets.delete_many({})
        await db.fee_structures.delete_many({})
        await db.invoices.delete_many({})
        await db.payments.delete_many({})
        await db.notices.delete_many({})
        await db.study_materials.delete_many({})
        await db.audit_logs.delete_many({})

    # 1. SuperAdmin Account
    admin = await db.users.find_one({"email": settings.DEFAULT_ADMIN_EMAIL.lower()})
    if not admin:
        admin_doc = {
            "email": settings.DEFAULT_ADMIN_EMAIL.lower(),
            "hashed_password": hash_password(settings.DEFAULT_ADMIN_PASSWORD),
            "full_name": settings.DEFAULT_ADMIN_NAME,
            "role": UserRole.SUPER_ADMIN.value,
            "phone": "+91 9830123456",
            "is_active": True,
            "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150",
            "created_at": datetime.now(timezone.utc),
        }
        res = await db.users.insert_one(admin_doc)
        admin_id = str(res.inserted_id)
        logger.info(f"Created SuperAdmin: {settings.DEFAULT_ADMIN_EMAIL}")
    else:
        admin_id = str(admin["_id"])

    # 2. Academic Sessions
    sessions = [
        {"label": "2024-2026", "start_year": 2024, "end_year": 2026, "is_current": True},
        {"label": "2023-2025", "start_year": 2023, "end_year": 2025, "is_current": False},
        {"label": "2025-2027", "start_year": 2025, "end_year": 2027, "is_current": False},
    ]
    for s in sessions:
        await db.academic_sessions.update_one({"label": s["label"]}, {"$set": s}, upsert=True)

    # 3. Courses
    courses = [
        {
            "code": "BED",
            "name": "Bachelor of Education (B.Ed.)",
            "department": "Department of Teacher Education",
            "duration_years": 2,
            "total_semesters": 4,
            "affiliation": "BSAEU (WBUTTEPA) & NCTE Recognized",
            "max_intake": 100,
            "description": "Comprehensive professional pre-service secondary teacher training curriculum.",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "code": "DELED",
            "name": "Diploma in Elementary Education (D.El.Ed.)",
            "department": "Department of Primary Education",
            "duration_years": 2,
            "total_semesters": 4,
            "affiliation": "WBBPE Recognized",
            "max_intake": 50,
            "description": "Foundational primary school teacher education and pedagogy course.",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "code": "BA_ED",
            "name": "B.A. (Honours) in Education",
            "department": "Department of Educational Studies",
            "duration_years": 3,
            "total_semesters": 6,
            "affiliation": "Calcutta University Affiliated",
            "max_intake": 60,
            "description": "Undergraduate degree focusing on educational sociology, philosophy, and history.",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        },
    ]
    for c in courses:
        await db.courses.update_one({"code": c["code"]}, {"$set": c}, upsert=True)

    # 4. Faculty Members
    faculty_list = [
        {
            "employee_id": "AMC-FAC-001",
            "full_name": "Dr. Debabrata Roy",
            "email": "debabrata.roy@annapurnacollege.org",
            "phone": "+91 9433123456",
            "department": "Department of Teacher Education",
            "designation": "Professor & Head of Department",
            "qualification": "M.Ed., Ph.D. in Education, UGC-NET",
            "specialization": "Curriculum Studies & Educational Philosophy",
            "joining_date": "2018-07-01",
            "assigned_subjects": ["BED-101", "BED-102"],
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=150",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "employee_id": "AMC-FAC-002",
            "full_name": "Prof. Mousumi Mukherjee",
            "email": "mousumi.m@annapurnacollege.org",
            "phone": "+91 9831987654",
            "department": "Department of Teacher Education",
            "designation": "Associate Professor",
            "qualification": "M.A. (English), M.Ed., WB-SET",
            "specialization": "Pedagogy of Language Teaching",
            "joining_date": "2019-08-15",
            "assigned_subjects": ["BED-103"],
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "employee_id": "AMC-FAC-003",
            "full_name": "Dr. Subhasish Das",
            "email": "subhasish.das@annapurnacollege.org",
            "phone": "+91 9732554433",
            "department": "Department of Teacher Education",
            "designation": "Assistant Professor",
            "qualification": "M.Sc. (Math), M.Ed., Ph.D.",
            "specialization": "Educational Psychology & Assessment",
            "joining_date": "2021-02-01",
            "assigned_subjects": ["BED-104"],
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "employee_id": "AMC-FAC-004",
            "full_name": "Smt. Priyanka Mondal",
            "email": "priyanka.mondal@annapurnacollege.org",
            "phone": "+91 9874112233",
            "department": "Department of Teacher Education",
            "designation": "Assistant Professor in Performing Arts",
            "qualification": "M.Mus., M.Ed.",
            "specialization": "Drama and Art in Education (EPC)",
            "joining_date": "2022-09-10",
            "assigned_subjects": ["BED-105"],
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=150",
            "created_at": datetime.now(timezone.utc),
        },
    ]

    faculty_ids = {}
    for f in faculty_list:
        res = await db.faculty.update_one({"employee_id": f["employee_id"]}, {"$set": f}, upsert=True)
        fac_rec = await db.faculty.find_one({"employee_id": f["employee_id"]})
        faculty_ids[f["employee_id"]] = str(fac_rec["_id"])

        # Also create faculty user login
        u_exists = await db.users.find_one({"email": f["email"]})
        if not u_exists:
            user_doc = {
                "email": f["email"],
                "hashed_password": hash_password("Teacher@Amce2024#"),
                "full_name": f["full_name"],
                "role": UserRole.FACULTY.value,
                "phone": f["phone"],
                "entity_id": str(fac_rec["_id"]),
                "is_active": True,
                "avatar_url": f["avatar_url"],
                "created_at": datetime.now(timezone.utc),
            }
            await db.users.insert_one(user_doc)

    # 5. Subjects for B.Ed. Semester 1
    subjects = [
        {
            "code": "BED-101",
            "title": "Childhood and Growing Up",
            "course_code": "BED",
            "semester": 1,
            "credits": 4,
            "full_marks": 100,
            "pass_marks": 40,
            "theory_marks": 70,
            "practical_marks": 30,
            "faculty_id": faculty_ids.get("AMC-FAC-001"),
            "faculty_name": "Dr. Debabrata Roy",
            "is_elective": False,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "code": "BED-102",
            "title": "Contemporary India and Education",
            "course_code": "BED",
            "semester": 1,
            "credits": 4,
            "full_marks": 100,
            "pass_marks": 40,
            "theory_marks": 70,
            "practical_marks": 30,
            "faculty_id": faculty_ids.get("AMC-FAC-001"),
            "faculty_name": "Dr. Debabrata Roy",
            "is_elective": False,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "code": "BED-103",
            "title": "Language Across the Curriculum",
            "course_code": "BED",
            "semester": 1,
            "credits": 2,
            "full_marks": 50,
            "pass_marks": 20,
            "theory_marks": 35,
            "practical_marks": 15,
            "faculty_id": faculty_ids.get("AMC-FAC-002"),
            "faculty_name": "Prof. Mousumi Mukherjee",
            "is_elective": False,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "code": "BED-104",
            "title": "Understanding Disciplines and Subjects",
            "course_code": "BED",
            "semester": 1,
            "credits": 2,
            "full_marks": 50,
            "pass_marks": 20,
            "theory_marks": 35,
            "practical_marks": 15,
            "faculty_id": faculty_ids.get("AMC-FAC-003"),
            "faculty_name": "Dr. Subhasish Das",
            "is_elective": False,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "code": "BED-105",
            "title": "Drama and Art in Education (EPC-1)",
            "course_code": "BED",
            "semester": 1,
            "credits": 2,
            "full_marks": 50,
            "pass_marks": 20,
            "theory_marks": 20,
            "practical_marks": 30,
            "faculty_id": faculty_ids.get("AMC-FAC-004"),
            "faculty_name": "Smt. Priyanka Mondal",
            "is_elective": False,
            "created_at": datetime.now(timezone.utc),
        },
    ]
    for s in subjects:
        await db.subjects.update_one({"code": s["code"]}, {"$set": s}, upsert=True)

    # 6. Students
    students_data = [
        {
            "roll_number": "AMC-BED-2024-001",
            "registration_number": "BSAEU-2024-81001",
            "full_name": "Ananya Das",
            "email": "ananya.das@student.annapurnacollege.org",
            "phone": "+91 9876001122",
            "course_code": "BED",
            "course_name": "Bachelor of Education (B.Ed.)",
            "academic_session": "2024-2026",
            "semester": 1,
            "section": "A",
            "date_of_birth": "2001-05-14",
            "gender": "FEMALE",
            "blood_group": "O+",
            "category": "GEN",
            "guardian_name": "Subir Das",
            "guardian_phone": "+91 9876001100",
            "guardian_relation": "Father",
            "address": "Kakdwip, South 24 Parganas, WB 743347",
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "roll_number": "AMC-BED-2024-002",
            "registration_number": "BSAEU-2024-81002",
            "full_name": "Souvik Halder",
            "email": "souvik.halder@student.annapurnacollege.org",
            "phone": "+91 9876002233",
            "course_code": "BED",
            "course_name": "Bachelor of Education (B.Ed.)",
            "academic_session": "2024-2026",
            "semester": 1,
            "section": "A",
            "date_of_birth": "2000-11-20",
            "gender": "MALE",
            "blood_group": "B+",
            "category": "SC",
            "guardian_name": "Prabir Halder",
            "guardian_phone": "+91 9876002200",
            "guardian_relation": "Father",
            "address": "Namkhana, South 24 Parganas, WB 743357",
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "roll_number": "AMC-BED-2024-003",
            "registration_number": "BSAEU-2024-81003",
            "full_name": "Rituparna Ghosh",
            "email": "rituparna.ghosh@student.annapurnacollege.org",
            "phone": "+91 9876003344",
            "course_code": "BED",
            "course_name": "Bachelor of Education (B.Ed.)",
            "academic_session": "2024-2026",
            "semester": 1,
            "section": "A",
            "date_of_birth": "2002-02-18",
            "gender": "FEMALE",
            "blood_group": "A+",
            "category": "OBC-B",
            "guardian_name": "Narayan Ghosh",
            "guardian_phone": "+91 9876003300",
            "guardian_relation": "Father",
            "address": "Diamond Harbour, South 24 Parganas, WB 743331",
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=150",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "roll_number": "AMC-BED-2024-004",
            "registration_number": "BSAEU-2024-81004",
            "full_name": "Sayan Banerjee",
            "email": "sayan.b@student.annapurnacollege.org",
            "phone": "+91 9876004455",
            "course_code": "BED",
            "course_name": "Bachelor of Education (B.Ed.)",
            "academic_session": "2024-2026",
            "semester": 1,
            "section": "A",
            "date_of_birth": "2001-08-09",
            "gender": "MALE",
            "blood_group": "AB+",
            "category": "GEN",
            "guardian_name": "Ashoke Banerjee",
            "guardian_phone": "+91 9876004400",
            "guardian_relation": "Father",
            "address": "Kulpi, South 24 Parganas, WB 743351",
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "roll_number": "AMC-BED-2024-005",
            "registration_number": "BSAEU-2024-81005",
            "full_name": "Tanmay Sarkar",
            "email": "tanmay.sarkar@student.annapurnacollege.org",
            "phone": "+91 9876005566",
            "course_code": "BED",
            "course_name": "Bachelor of Education (B.Ed.)",
            "academic_session": "2024-2026",
            "semester": 1,
            "section": "A",
            "date_of_birth": "1999-12-05",
            "gender": "MALE",
            "blood_group": "O-",
            "category": "SC",
            "guardian_name": "Dulal Sarkar",
            "guardian_phone": "+91 9876005500",
            "guardian_relation": "Father",
            "address": "Patharpratima, Sundarban, WB 743371",
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=150",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "roll_number": "AMC-BED-2024-006",
            "registration_number": "BSAEU-2024-81006",
            "full_name": "Deblina Chakraborty",
            "email": "deblina.c@student.annapurnacollege.org",
            "phone": "+91 9876006677",
            "course_code": "BED",
            "course_name": "Bachelor of Education (B.Ed.)",
            "academic_session": "2024-2026",
            "semester": 1,
            "section": "A",
            "date_of_birth": "2001-04-12",
            "gender": "FEMALE",
            "blood_group": "A-",
            "category": "GEN",
            "guardian_name": "Amitabha Chakraborty",
            "guardian_phone": "+91 9876006600",
            "guardian_relation": "Father",
            "address": "Kakdwip Bazar, South 24 Parganas, WB 743347",
            "status": "ACTIVE",
            "avatar_url": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=150",
            "created_at": datetime.now(timezone.utc),
        },
    ]

    student_records = []
    for s in students_data:
        await db.students.update_one({"roll_number": s["roll_number"]}, {"$set": s}, upsert=True)
        rec = await db.students.find_one({"roll_number": s["roll_number"]})
        student_records.append(rec)

        # Create user account for student
        u_exists = await db.users.find_one({"email": s["email"]})
        if not u_exists:
            user_doc = {
                "email": s["email"],
                "hashed_password": hash_password("Student@Amce2024#"),
                "full_name": s["full_name"],
                "role": UserRole.STUDENT.value,
                "phone": s["phone"],
                "entity_id": str(rec["_id"]),
                "is_active": True,
                "avatar_url": s["avatar_url"],
                "created_at": datetime.now(timezone.utc),
            }
            await db.users.insert_one(user_doc)

    # 7. Examination
    exam_doc = {
        "code": "BED-SEM1-FINAL-2024",
        "title": "B.Ed. 1st Semester Final University Examination 2024",
        "course_code": "BED",
        "semester": 1,
        "academic_session": "2024-2026",
        "exam_type": "SEMESTER_FINAL",
        "start_date": "2024-12-10",
        "end_date": "2024-12-22",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    await db.examinations.update_one({"code": exam_doc["code"]}, {"$set": exam_doc}, upsert=True)
    exam_rec = await db.examinations.find_one({"code": exam_doc["code"]})
    exam_id = str(exam_rec["_id"])

    # 8. Marksheets across the workflow stages
    # Student 1: PUBLISHED (Outstanding)
    # Student 2: ADMIN_APPROVED
    # Student 3: DEPARTMENT_VERIFIED
    # Student 4: SUBMITTED_BY_FACULTY
    # Student 5: DRAFT
    # Student 6: REJECTED (with remarks)

    sample_marks_profiles = [
        # Student 1 - PUBLISHED
        {
            "scores": [
                {"code": "BED-101", "title": "Childhood and Growing Up", "t": 62, "p": 27, "mt": 70, "mp": 30},
                {"code": "BED-102", "title": "Contemporary India and Education", "t": 59, "p": 28, "mt": 70, "mp": 30},
                {"code": "BED-103", "title": "Language Across the Curriculum", "t": 31, "p": 14, "mt": 35, "mp": 15},
                {"code": "BED-104", "title": "Understanding Disciplines and Subjects", "t": 29, "p": 13, "mt": 35, "mp": 15},
                {"code": "BED-105", "title": "Drama and Art in Education (EPC-1)", "t": 18, "p": 28, "mt": 20, "mp": 30},
            ],
            "status": MarksheetStatus.PUBLISHED.value,
        },
        # Student 2 - ADMIN_APPROVED
        {
            "scores": [
                {"code": "BED-101", "title": "Childhood and Growing Up", "t": 54, "p": 24, "mt": 70, "mp": 30},
                {"code": "BED-102", "title": "Contemporary India and Education", "t": 52, "p": 25, "mt": 70, "mp": 30},
                {"code": "BED-103", "title": "Language Across the Curriculum", "t": 27, "p": 12, "mt": 35, "mp": 15},
                {"code": "BED-104", "title": "Understanding Disciplines and Subjects", "t": 26, "p": 11, "mt": 35, "mp": 15},
                {"code": "BED-105", "title": "Drama and Art in Education (EPC-1)", "t": 16, "p": 26, "mt": 20, "mp": 30},
            ],
            "status": MarksheetStatus.ADMIN_APPROVED.value,
        },
        # Student 3 - DEPARTMENT_VERIFIED
        {
            "scores": [
                {"code": "BED-101", "title": "Childhood and Growing Up", "t": 58, "p": 26, "mt": 70, "mp": 30},
                {"code": "BED-102", "title": "Contemporary India and Education", "t": 57, "p": 26, "mt": 70, "mp": 30},
                {"code": "BED-103", "title": "Language Across the Curriculum", "t": 29, "p": 13, "mt": 35, "mp": 15},
                {"code": "BED-104", "title": "Understanding Disciplines and Subjects", "t": 28, "p": 12, "mt": 35, "mp": 15},
                {"code": "BED-105", "title": "Drama and Art in Education (EPC-1)", "t": 17, "p": 27, "mt": 20, "mp": 30},
            ],
            "status": MarksheetStatus.DEPARTMENT_VERIFIED.value,
        },
        # Student 4 - SUBMITTED_BY_FACULTY
        {
            "scores": [
                {"code": "BED-101", "title": "Childhood and Growing Up", "t": 48, "p": 22, "mt": 70, "mp": 30},
                {"code": "BED-102", "title": "Contemporary India and Education", "t": 49, "p": 21, "mt": 70, "mp": 30},
                {"code": "BED-103", "title": "Language Across the Curriculum", "t": 24, "p": 10, "mt": 35, "mp": 15},
                {"code": "BED-104", "title": "Understanding Disciplines and Subjects", "t": 25, "p": 11, "mt": 35, "mp": 15},
                {"code": "BED-105", "title": "Drama and Art in Education (EPC-1)", "t": 15, "p": 24, "mt": 20, "mp": 30},
            ],
            "status": MarksheetStatus.SUBMITTED_BY_FACULTY.value,
        },
        # Student 5 - DRAFT
        {
            "scores": [
                {"code": "BED-101", "title": "Childhood and Growing Up", "t": 42, "p": 20, "mt": 70, "mp": 30},
                {"code": "BED-102", "title": "Contemporary India and Education", "t": 44, "p": 20, "mt": 70, "mp": 30},
                {"code": "BED-103", "title": "Language Across the Curriculum", "t": 22, "p": 10, "mt": 35, "mp": 15},
                {"code": "BED-104", "title": "Understanding Disciplines and Subjects", "t": 21, "p": 9, "mt": 35, "mp": 15},
                {"code": "BED-105", "title": "Drama and Art in Education (EPC-1)", "t": 14, "p": 22, "mt": 20, "mp": 30},
            ],
            "status": MarksheetStatus.DRAFT.value,
        },
        # Student 6 - REJECTED
        {
            "scores": [
                {"code": "BED-101", "title": "Childhood and Growing Up", "t": 35, "p": 18, "mt": 70, "mp": 30},
                {"code": "BED-102", "title": "Contemporary India and Education", "t": 38, "p": 19, "mt": 70, "mp": 30},
                {"code": "BED-103", "title": "Language Across the Curriculum", "t": 18, "p": 8, "mt": 35, "mp": 15},
                {"code": "BED-104", "title": "Understanding Disciplines and Subjects", "t": 19, "p": 8, "mt": 35, "mp": 15},
                {"code": "BED-105", "title": "Drama and Art in Education (EPC-1)", "t": 12, "p": 20, "mt": 20, "mp": 30},
            ],
            "status": MarksheetStatus.REJECTED.value,
            "rejection_reason": "Practical marks mismatch with internal assessment register. Please re-verify.",
        },
    ]

    for idx, prof in enumerate(sample_marks_profiles):
        if idx >= len(student_records):
            break
        st = student_records[idx]
        st_id = str(st["_id"])

        score_inputs = []
        for sc in prof["scores"]:
            from annapurna_memorial_college_erp_backend.schemas.examination import SubjectScoreInput
            score_inputs.append(
                SubjectScoreInput(
                    subject_code=sc["code"],
                    subject_title=sc["title"],
                    credits=4 if "101" in sc["code"] or "102" in sc["code"] else 2,
                    theory_obtained=sc["t"],
                    practical_obtained=sc["p"],
                    max_theory=sc["mt"],
                    max_practical=sc["mp"],
                )
            )

        (
            processed_scores,
            total_obtained,
            grand_max,
            percentage,
            sgpa,
            result_status,
        ) = marksheet_service.process_subject_scores(score_inputs)

        v_hash = marksheet_service.generate_verification_hash(st_id, exam_id, sgpa)

        ms_status = prof["status"]
        audit_trail = [
            {
                "stage": "DRAFT",
                "performed_by_id": faculty_ids.get("AMC-FAC-001"),
                "performed_by_name": "Dr. Debabrata Roy",
                "performed_by_role": "FACULTY",
                "timestamp": datetime.now(timezone.utc) - timedelta(days=5),
                "action": "MARKS_ENTERED",
                "remarks": "Initial marks calculated and verified against exam booklets.",
            }
        ]

        if ms_status in [MarksheetStatus.SUBMITTED_BY_FACULTY.value, MarksheetStatus.DEPARTMENT_VERIFIED.value, MarksheetStatus.ADMIN_APPROVED.value, MarksheetStatus.PUBLISHED.value]:
            audit_trail.append({
                "stage": MarksheetStatus.SUBMITTED_BY_FACULTY.value,
                "performed_by_id": faculty_ids.get("AMC-FAC-001"),
                "performed_by_name": "Dr. Debabrata Roy",
                "performed_by_role": "FACULTY",
                "timestamp": datetime.now(timezone.utc) - timedelta(days=4),
                "action": "SUBMIT",
                "remarks": "Submitted for Department verification.",
            })

        if ms_status in [MarksheetStatus.DEPARTMENT_VERIFIED.value, MarksheetStatus.ADMIN_APPROVED.value, MarksheetStatus.PUBLISHED.value]:
            audit_trail.append({
                "stage": MarksheetStatus.DEPARTMENT_VERIFIED.value,
                "performed_by_id": admin_id,
                "performed_by_name": "Academic Coordinator",
                "performed_by_role": "ADMIN",
                "timestamp": datetime.now(timezone.utc) - timedelta(days=3),
                "action": "VERIFY",
                "remarks": "Internal assessment cross-checked with attendance register.",
            })

        if ms_status in [MarksheetStatus.ADMIN_APPROVED.value, MarksheetStatus.PUBLISHED.value]:
            audit_trail.append({
                "stage": MarksheetStatus.ADMIN_APPROVED.value,
                "performed_by_id": admin_id,
                "performed_by_name": settings.DEFAULT_ADMIN_NAME,
                "performed_by_role": "SUPER_ADMIN",
                "timestamp": datetime.now(timezone.utc) - timedelta(days=2),
                "action": "APPROVE",
                "remarks": "Approved by Principal for final result publication.",
            })

        if ms_status == MarksheetStatus.PUBLISHED.value:
            audit_trail.append({
                "stage": MarksheetStatus.PUBLISHED.value,
                "performed_by_id": admin_id,
                "performed_by_name": settings.DEFAULT_ADMIN_NAME,
                "performed_by_role": "SUPER_ADMIN",
                "timestamp": datetime.now(timezone.utc) - timedelta(days=1),
                "action": "PUBLISH",
                "remarks": "Published to student portal with digital certification.",
            })

        if ms_status == MarksheetStatus.REJECTED.value:
            audit_trail.append({
                "stage": MarksheetStatus.REJECTED.value,
                "performed_by_id": admin_id,
                "performed_by_name": "Academic Coordinator",
                "performed_by_role": "ADMIN",
                "timestamp": datetime.now(timezone.utc) - timedelta(days=1),
                "action": "REJECT",
                "remarks": prof.get("rejection_reason"),
            })

        m_doc = {
            "exam_id": exam_id,
            "exam_title": exam_doc["title"],
            "student_id": st_id,
            "roll_number": st["roll_number"],
            "registration_number": st["registration_number"],
            "student_name": st["full_name"],
            "course_code": "BED",
            "course_name": "Bachelor of Education (B.Ed.)",
            "semester": 1,
            "academic_session": "2024-2026",
            "subject_scores": [s.model_dump() for s in processed_scores],
            "total_marks_obtained": total_obtained,
            "grand_max_marks": grand_max,
            "overall_percentage": percentage,
            "sgpa": sgpa,
            "cgpa": sgpa,
            "letter_grade": processed_scores[0].letter_grade,
            "result_status": result_status,
            "status": ms_status,
            "qr_code_hash": v_hash,
            "rejection_reason": prof.get("rejection_reason"),
            "audit_trail": audit_trail,
            "created_at": datetime.now(timezone.utc) - timedelta(days=5),
            "updated_at": datetime.now(timezone.utc),
        }
        await db.marksheets.update_one(
            {"exam_id": exam_id, "student_id": st_id},
            {"$set": m_doc},
            upsert=True,
        )

    # 9. Attendance Samples
    for day_offset in range(5):
        att_date = (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        att_doc = {
            "date": att_date,
            "course_code": "BED",
            "semester": 1,
            "section": "A",
            "subject_code": "BED-101",
            "faculty_id": faculty_ids.get("AMC-FAC-001"),
            "faculty_name": "Dr. Debabrata Roy",
            "records": [
                {
                    "student_id": str(st["_id"]),
                    "roll_number": st["roll_number"],
                    "student_name": st["full_name"],
                    "status": "PRESENT" if idx != 4 or day_offset % 2 == 0 else "ABSENT",
                }
                for idx, st in enumerate(student_records)
            ],
            "total_students": len(student_records),
            "present_count": len(student_records) - (1 if day_offset % 2 != 0 else 0),
            "absent_count": 1 if day_offset % 2 != 0 else 0,
            "percentage": 83.3 if day_offset % 2 != 0 else 100.0,
            "created_at": datetime.now(timezone.utc),
        }
        await db.attendance.update_one(
            {"date": att_date, "course_code": "BED", "semester": 1, "subject_code": "BED-101"},
            {"$set": att_doc},
            upsert=True,
        )

    # 10. Fee Structure & Invoices
    fee_struct_doc = {
        "title": "B.Ed. 1st Semester Academic Fee Structure 2024-2026",
        "course_code": "BED",
        "academic_session": "2024-2026",
        "semester": 1,
        "components": [
            {"name": "Tuition Fee", "amount": 22000.0},
            {"name": "Practicum & Lab Charges", "amount": 6000.0},
            {"name": "Development & Infrastructure Fee", "amount": 4000.0},
            {"name": "Library & Digital Resources Fee", "amount": 2000.0},
            {"name": "Examination & Affiliation Fee", "amount": 1000.0},
        ],
        "total_amount": 35000.0,
        "due_date": "2024-11-30",
        "created_at": datetime.now(timezone.utc),
    }
    await db.fee_structures.update_one({"title": fee_struct_doc["title"]}, {"$set": fee_struct_doc}, upsert=True)

    # Seed Invoices for Students
    invoice_statuses = [
        {"paid": 35000.0, "status": "PAID"},
        {"paid": 20000.0, "status": "PARTIAL"},
        {"paid": 35000.0, "status": "PAID"},
        {"paid": 0.0, "status": "UNPAID"},
        {"paid": 15000.0, "status": "PARTIAL"},
        {"paid": 35000.0, "status": "PAID"},
    ]
    for idx, st in enumerate(student_records):
        st_id = str(st["_id"])
        inv_stat = invoice_statuses[idx % len(invoice_statuses)]
        inv_num = f"INV-2024-{1001 + idx}"
        due_amount = 35000.0
        paid_amount = inv_stat["paid"]
        balance = max(0.0, due_amount - paid_amount)

        inv_doc = {
            "invoice_number": inv_num,
            "student_id": st_id,
            "roll_number": st["roll_number"],
            "student_name": st["full_name"],
            "course_code": "BED",
            "academic_session": "2024-2026",
            "semester": 1,
            "amount_due": due_amount,
            "amount_paid": paid_amount,
            "balance": balance,
            "status": inv_stat["status"],
            "due_date": "2024-11-30",
            "components": fee_struct_doc["components"],
            "created_at": datetime.now(timezone.utc),
        }
        await db.invoices.update_one({"invoice_number": inv_num}, {"$set": inv_doc}, upsert=True)

        if paid_amount > 0:
            pay_doc = {
                "payment_number": f"PAY-2024-{5001 + idx}",
                "invoice_id": inv_num,
                "student_id": st_id,
                "student_name": st["full_name"],
                "roll_number": st["roll_number"],
                "amount": paid_amount,
                "payment_method": "UPI" if idx % 2 == 0 else "BANK_TRANSFER",
                "transaction_id": f"UPI-SBIN-{idx}92837482",
                "payment_date": datetime.now(timezone.utc) - timedelta(days=idx * 2),
                "received_by_name": "Accounts Officer",
                "notes": "Semester fee payment verified against SBI merchant ledger.",
                "created_at": datetime.now(timezone.utc),
            }
            await db.payments.update_one({"payment_number": pay_doc["payment_number"]}, {"$set": pay_doc}, upsert=True)

    # 11. Notices
    notices_data = [
        {
            "title": "Official Release of B.Ed. 1st Semester Marksheets (2024-2026 Batch)",
            "content": "The statement of marks for B.Ed. 1st Semester Final Examination 2024 has been verified and published. Students can view their grades and download verified electronic marksheets from the student portal.",
            "category": "EXAMINATION",
            "target_audience": "ALL",
            "priority": "HIGH",
            "is_pinned": True,
            "published_by_name": "Controller of Examinations",
            "views_count": 142,
            "created_at": datetime.now(timezone.utc) - timedelta(days=1),
        },
        {
            "title": "NCTE Mandatory Biometric Attendance & Practicum File Submission",
            "content": "All B.Ed. teacher trainees are reminded that minimum 80% physical attendance in instructional classes and 90% attendance in school internship / practicum sessions is mandatory as per NCTE norms.",
            "category": "ACADEMIC",
            "target_audience": "STUDENTS",
            "priority": "URGENT",
            "is_pinned": True,
            "published_by_name": "Principal's Office",
            "views_count": 98,
            "created_at": datetime.now(timezone.utc) - timedelta(days=2),
        },
        {
            "title": "Faculty Departmental Meeting on Lesson Planning & Micro-Teaching",
            "content": "A departmental academic review meeting will be held on Monday at 3:00 PM in the Faculty Conference Room to finalize the micro-teaching observation schedule.",
            "category": "ADMINISTRATIVE",
            "target_audience": "FACULTY",
            "priority": "NORMAL",
            "is_pinned": False,
            "published_by_name": "Dr. Debabrata Roy (HOD)",
            "views_count": 28,
            "created_at": datetime.now(timezone.utc) - timedelta(days=3),
        },
    ]
    for n in notices_data:
        await db.notices.update_one({"title": n["title"]}, {"$set": n}, upsert=True)

    # 12. Study Materials
    materials = [
        {
            "title": "Unit 1: Theories of Child Development (Piaget, Vygotsky, Kohlberg)",
            "description": "Comprehensive analytical lecture notes covering cognitive, socio-cultural, and moral development stages for B.Ed. Course BED-101.",
            "course_code": "BED",
            "semester": 1,
            "subject_code": "BED-101",
            "file_url": "https://example.com/materials/bed101_theories_of_childhood.pdf",
            "file_type": "pdf",
            "file_size_bytes": 4820000,
            "tags": ["Psychology", "Piaget", "Vygotsky", "Childhood"],
            "uploaded_by_name": "Dr. Debabrata Roy",
            "downloads_count": 87,
            "created_at": datetime.now(timezone.utc) - timedelta(days=10),
        },
        {
            "title": "Constitutional Provisions for Education in Independent India",
            "description": "Study material covering Articles 15, 21A, 28, 29, 30, and 45 of Indian Constitution related to universal elementary education.",
            "course_code": "BED",
            "semester": 1,
            "subject_code": "BED-102",
            "file_url": "https://example.com/materials/bed102_constitutional_provisions.pdf",
            "file_type": "pdf",
            "file_size_bytes": 3120000,
            "tags": ["Constitution", "Right to Education", "Policy"],
            "uploaded_by_name": "Prof. Mousumi Mukherjee",
            "downloads_count": 64,
            "created_at": datetime.now(timezone.utc) - timedelta(days=8),
        },
    ]
    for m in materials:
        await db.study_materials.update_one({"title": m["title"]}, {"$set": m}, upsert=True)

    logger.info("Database seeding successfully completed for Annapurna Memorial College ERP!")


if __name__ == "__main__":
    asyncio.run(seed_all(force=True))
