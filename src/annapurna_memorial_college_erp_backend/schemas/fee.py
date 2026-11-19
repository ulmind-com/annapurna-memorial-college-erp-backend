from typing import List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class PaymentStatus(str, Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"


class PaymentMethod(str, Enum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    UPI = "UPI"
    CHEQUE = "CHEQUE"
    CARD = "CARD"


class FeeComponent(BaseModel):
    name: str  # Tuition Fee, Development Fee, Lab/Practicum Fee, Library Fee, Exam Fee
    amount: float


class FeeStructureBase(BaseModel):
    title: str
    course_code: str
    academic_session: str
    semester: int
    components: List[FeeComponent]
    total_amount: float
    due_date: str


class FeeStructureCreate(FeeStructureBase):
    pass


class FeeStructureResponse(FeeStructureBase):
    id: str
    created_at: datetime


class InvoiceBase(BaseModel):
    student_id: str
    course_code: str
    academic_session: str
    semester: int
    amount_due: float
    due_date: str
    components: List[FeeComponent] = []


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    student_id: str
    roll_number: str
    student_name: str
    course_code: str
    academic_session: str
    semester: int
    amount_due: float
    amount_paid: float
    balance: float
    status: PaymentStatus
    due_date: str
    components: List[FeeComponent]
    created_at: datetime


class PaymentCreate(BaseModel):
    invoice_id: str
    amount: float
    payment_method: PaymentMethod = PaymentMethod.UPI
    transaction_id: Optional[str] = None
    notes: Optional[str] = None


class PaymentResponse(BaseModel):
    id: str
    payment_number: str
    invoice_id: str
    student_id: str
    student_name: str
    roll_number: str
    amount: float
    payment_method: PaymentMethod
    transaction_id: str
    payment_date: datetime
    received_by_name: str
    receipt_url: Optional[str] = None
    notes: Optional[str] = None
