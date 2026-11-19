from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ExamType(str, Enum):
    MID_TERM = "MID_TERM"
    INTERNAL_ASSESSMENT = "INTERNAL_ASSESSMENT"
    SEMESTER_FINAL = "SEMESTER_FINAL"
    PRACTICUM = "PRACTICUM"


class MarksheetStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED_BY_FACULTY = "SUBMITTED_BY_FACULTY"
    DEPARTMENT_VERIFIED = "DEPARTMENT_VERIFIED"
    ADMIN_APPROVED = "ADMIN_APPROVED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"


class ExaminationBase(BaseModel):
    code: str
    title: str
    course_code: str
    semester: int
    academic_session: str
    exam_type: ExamType = ExamType.SEMESTER_FINAL
    start_date: str
    end_date: str
    is_active: bool = True


class ExaminationCreate(ExaminationBase):
    pass


class ExaminationResponse(ExaminationBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class SubjectScoreInput(BaseModel):
    subject_code: str
    subject_title: str
    credits: int = 4
    theory_obtained: float = 0.0
    practical_obtained: float = 0.0
    max_theory: float = 70.0
    max_practical: float = 30.0
    remarks: Optional[str] = None


class SubjectScoreOutput(SubjectScoreInput):
    total_obtained: float
    max_marks: float
    percentage: float
    grade_point: float
    letter_grade: str


class AuditTrailEntry(BaseModel):
    stage: str
    performed_by_id: str
    performed_by_name: str
    performed_by_role: str
    timestamp: datetime
    action: str
    remarks: Optional[str] = None


class MarksheetCreate(BaseModel):
    exam_id: str
    student_id: str
    subject_scores: List[SubjectScoreInput]


class MarksheetBulkInput(BaseModel):
    exam_id: str
    marksheets: List[MarksheetCreate]


class MarksheetWorkflowAction(BaseModel):
    action: str  # SUBMIT, VERIFY, APPROVE, PUBLISH, REJECT
    remarks: Optional[str] = None


class MarksheetResponse(BaseModel):
    id: str
    exam_id: str
    exam_title: str
    student_id: str
    roll_number: str
    registration_number: Optional[str] = None
    student_name: str
    course_code: str
    course_name: str
    semester: int
    academic_session: str
    subject_scores: List[SubjectScoreOutput]
    total_marks_obtained: float
    grand_max_marks: float
    overall_percentage: float
    sgpa: float
    cgpa: float
    letter_grade: str
    result_status: str  # FIRST CLASS WITH DISTINCTION, FIRST CLASS, SECOND CLASS, PASS, SUPPLEMENTARY, FAIL
    status: MarksheetStatus
    qr_code_hash: str
    faculty_submitted_by: Optional[str] = None
    faculty_submitted_at: Optional[datetime] = None
    department_verified_by: Optional[str] = None
    department_verified_at: Optional[datetime] = None
    admin_approved_by: Optional[str] = None
    admin_approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    audit_trail: List[AuditTrailEntry] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
