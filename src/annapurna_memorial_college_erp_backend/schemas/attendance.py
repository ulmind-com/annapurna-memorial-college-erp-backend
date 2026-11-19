from typing import List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    EXCUSED = "EXCUSED"


class AttendanceItem(BaseModel):
    student_id: str
    roll_number: str
    student_name: str
    status: AttendanceStatus = AttendanceStatus.PRESENT
    remarks: Optional[str] = None


class AttendanceRecordCreate(BaseModel):
    date: str  # YYYY-MM-DD
    course_code: str
    semester: int
    section: str = "A"
    subject_code: str
    records: List[AttendanceItem]


class AttendanceRecordResponse(AttendanceRecordCreate):
    id: str
    faculty_id: Optional[str] = None
    faculty_name: Optional[str] = None
    total_students: int
    present_count: int
    absent_count: int
    percentage: float
    created_at: datetime


class StudentAttendanceSummary(BaseModel):
    student_id: str
    roll_number: str
    student_name: str
    course_code: str
    semester: int
    total_classes: int
    classes_attended: int
    percentage: float
    is_short_attendance: bool  # Below 75%
