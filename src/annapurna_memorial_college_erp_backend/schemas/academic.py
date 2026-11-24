from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class AcademicSessionBase(BaseModel):
    label: str  # e.g., "2024-2026"
    start_year: int
    end_year: int
    is_current: bool = False


class AcademicSessionCreate(AcademicSessionBase):
    pass


class AcademicSessionResponse(AcademicSessionBase):
    id: str


class CourseBase(BaseModel):
    code: str  # e.g. "BED", "DELED", "BA_ED"
    name: str  # e.g. "Bachelor of Education (B.Ed.)"
    department: str
    duration_years: int = 2
    total_semesters: int = 4
    affiliation: str = "BSAEU & NCTE Recognized"
    max_intake: int = 100
    description: Optional[str] = None
    is_active: bool = True


class CourseCreate(CourseBase):
    pass


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    duration_years: Optional[int] = None
    total_semesters: Optional[int] = None
    affiliation: Optional[str] = None
    max_intake: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CourseResponse(CourseBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class SubjectBase(BaseModel):
    code: str  # e.g. "BED-101"
    title: str
    course_code: str
    semester: int
    credits: int = 4
    full_marks: int = 100
    pass_marks: int = 40
    theory_marks: int = 70
    practical_marks: int = 30
    faculty_id: Optional[str] = None
    is_elective: bool = False


class SubjectCreate(SubjectBase):
    pass


class SubjectUpdate(BaseModel):
    title: Optional[str] = None
    credits: Optional[int] = None
    full_marks: Optional[int] = None
    pass_marks: Optional[int] = None
    theory_marks: Optional[int] = None
    practical_marks: Optional[int] = None
    faculty_id: Optional[str] = None
    is_elective: Optional[bool] = None


class SubjectResponse(SubjectBase):
    id: str
    faculty_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class TimetableSlotBase(BaseModel):
    day: str  # MON, TUE, WED, THU, FRI, SAT
    course_code: str
    semester: int
    time: str
    subject: str
    class_label: Optional[str] = None
    room: Optional[str] = "Room 101"
    faculty: Optional[str] = "Faculty Member"
    type: Optional[str] = "Theory Lecture"
    status: Optional[str] = "Scheduled"


class TimetableSlotCreate(TimetableSlotBase):
    pass

