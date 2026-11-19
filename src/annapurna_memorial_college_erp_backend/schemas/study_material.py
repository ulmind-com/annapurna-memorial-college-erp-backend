from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class StudyMaterialBase(BaseModel):
    title: str
    description: Optional[str] = None
    course_code: str
    semester: int
    subject_code: str
    file_url: str
    file_type: str = "pdf"
    file_size_bytes: int = 0
    tags: List[str] = []


class StudyMaterialCreate(StudyMaterialBase):
    pass


class StudyMaterialResponse(StudyMaterialBase):
    id: str
    uploaded_by_id: str
    uploaded_by_name: str
    downloads_count: int = 0
    created_at: datetime
