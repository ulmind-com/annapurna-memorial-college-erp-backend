import uuid
from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from annapurna_memorial_college_erp_backend.database import get_db
from annapurna_memorial_college_erp_backend.security import (
    get_current_user,
    require_roles,
    UserRole,
)
from annapurna_memorial_college_erp_backend.schemas.fee import (
    FeeStructureCreate,
    InvoiceCreate,
    PaymentCreate,
    PaymentStatus,
    PaymentMethod,
)
from annapurna_memorial_college_erp_backend.services.audit_service import audit_service

router = APIRouter(prefix="/fees", tags=["Fee Management & Accounts"])


# FEE STRUCTURES
@router.get("/structures")
async def list_fee_structures(
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if course_code:
        query["course_code"] = course_code
    if semester:
        query["semester"] = semester

    cursor = db.fee_structures.find(query).sort("created_at", -1)
    structures = []
    async for s in cursor:
        structures.append({
            "id": str(s["_id"]),
            "title": s["title"],
            "course_code": s["course_code"],
            "academic_session": s["academic_session"],
            "semester": s["semester"],
            "components": s.get("components", []),
            "total_amount": s["total_amount"],
            "due_date": s["due_date"],
            "created_at": s.get("created_at"),
        })
    return structures


@router.post("/structures", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.STAFF]))])
async def create_fee_structure(req: FeeStructureCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    doc = req.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    res = await db.fee_structures.insert_one(doc)
    doc.pop("_id", None)
    return {"id": str(res.inserted_id), **doc}


# INVOICES
@router.get("/invoices")
async def list_invoices(
    student_id: Optional[str] = None,
    course_code: Optional[str] = None,
    semester: Optional[int] = None,
    status: Optional[PaymentStatus] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    query = {}
    if student_id:
        query["student_id"] = student_id
    if course_code:
        query["course_code"] = course_code
    if semester:
        query["semester"] = semester
    if status:
        query["status"] = status.value

    # If student, constrain to their own invoices
    if current_user.get("role") == UserRole.STUDENT.value:
        query["student_id"] = current_user.get("entity_id")

    total = await db.invoices.count_documents(query)
    cursor = db.invoices.find(query).skip((page - 1) * limit).limit(limit).sort("created_at", -1)
    invoices = []
    async for inv in cursor:
        invoices.append({
            "id": str(inv["_id"]),
            "invoice_number": inv["invoice_number"],
            "student_id": inv["student_id"],
            "roll_number": inv.get("roll_number", ""),
            "student_name": inv.get("student_name", ""),
            "course_code": inv["course_code"],
            "academic_session": inv["academic_session"],
            "semester": inv["semester"],
            "amount_due": inv["amount_due"],
            "amount_paid": inv.get("amount_paid", 0.0),
            "balance": inv.get("balance", inv["amount_due"]),
            "status": inv.get("status", PaymentStatus.UNPAID.value),
            "due_date": inv["due_date"],
            "components": inv.get("components", []),
            "created_at": inv.get("created_at"),
        })

    return {
        "items": invoices,
        "total": total,
        "page": page,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
    }


@router.post("/invoices/generate", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.STAFF]))])
async def generate_invoices_for_batch(
    course_code: str,
    semester: int,
    academic_session: str,
    fee_structure_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Bulk generates invoices for all active students in a course & semester
    """
    db = await get_db()
    fee_struct = await db.fee_structures.find_one({"_id": ObjectId(fee_structure_id)})
    if not fee_struct:
        raise HTTPException(status_code=404, detail="Fee structure not found.")

    students_cursor = db.students.find({
        "course_code": course_code,
        "semester": semester,
        "academic_session": academic_session,
        "status": "ACTIVE",
    })

    created_count = 0
    year_prefix = datetime.now().strftime("%Y")
    async for s in students_cursor:
        student_id = str(s["_id"])
        # Check if invoice already exists
        exists = await db.invoices.find_one({
            "student_id": student_id,
            "course_code": course_code,
            "semester": semester,
        })
        if not exists:
            inv_number = f"INV-{year_prefix}-{uuid.uuid4().hex[:6].upper()}"
            inv_doc = {
                "invoice_number": inv_number,
                "student_id": student_id,
                "roll_number": s["roll_number"],
                "student_name": s["full_name"],
                "course_code": course_code,
                "academic_session": academic_session,
                "semester": semester,
                "amount_due": fee_struct["total_amount"],
                "amount_paid": 0.0,
                "balance": fee_struct["total_amount"],
                "status": PaymentStatus.UNPAID.value,
                "due_date": fee_struct["due_date"],
                "components": fee_struct.get("components", []),
                "created_at": datetime.now(timezone.utc),
            }
            await db.invoices.insert_one(inv_doc)
            created_count += 1

    return {"message": f"Successfully generated {created_count} invoices.", "count": created_count}


# PAYMENTS
@router.post("/payments", dependencies=[Depends(require_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.STAFF]))])
async def record_payment(req: PaymentCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    invoice = await db.invoices.find_one({"_id": ObjectId(req.invoice_id)})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than 0.")

    new_paid = invoice.get("amount_paid", 0.0) + req.amount
    balance = max(0.0, invoice["amount_due"] - new_paid)

    new_status = PaymentStatus.PAID.value if balance <= 0 else PaymentStatus.PARTIAL.value

    txn_id = req.transaction_id or f"TXN-{uuid.uuid4().hex[:10].upper()}"
    pay_number = f"PAY-{uuid.uuid4().hex[:8].upper()}"

    payment_doc = {
        "payment_number": pay_number,
        "invoice_id": req.invoice_id,
        "student_id": invoice["student_id"],
        "student_name": invoice["student_name"],
        "roll_number": invoice["roll_number"],
        "amount": req.amount,
        "payment_method": req.payment_method.value,
        "transaction_id": txn_id,
        "payment_date": datetime.now(timezone.utc),
        "received_by_id": current_user["id"],
        "received_by_name": current_user.get("name", "Accountant"),
        "notes": req.notes,
        "created_at": datetime.now(timezone.utc),
    }

    await db.payments.insert_one(payment_doc)

    # Update invoice
    await db.invoices.update_one(
        {"_id": ObjectId(req.invoice_id)},
        {"$set": {"amount_paid": new_paid, "balance": balance, "status": new_status, "updated_at": datetime.now(timezone.utc)}},
    )

    await audit_service.log_action(
        action="FEE_PAYMENT_RECORDED",
        entity_type="PAYMENT",
        user_id=current_user["id"],
        user_email=current_user["email"],
        user_role=current_user["role"],
        details={"invoice_id": req.invoice_id, "amount": req.amount, "txn_id": txn_id},
    )

    return {
        "message": "Payment recorded successfully",
        "payment_number": pay_number,
        "new_balance": balance,
        "invoice_status": new_status,
    }


@router.get("/overview")
async def get_fee_overview(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    # Aggregation for summary
    invoices = await db.invoices.find().to_list(length=5000)
    total_billed = sum(i.get("amount_due", 0.0) for i in invoices)
    total_collected = sum(i.get("amount_paid", 0.0) for i in invoices)
    total_outstanding = max(0.0, total_billed - total_collected)

    paid_count = sum(1 for i in invoices if i.get("status") == PaymentStatus.PAID.value)
    unpaid_count = sum(1 for i in invoices if i.get("status") == PaymentStatus.UNPAID.value)
    partial_count = sum(1 for i in invoices if i.get("status") == PaymentStatus.PARTIAL.value)

    return {
        "total_billed": round(total_billed, 2),
        "total_collected": round(total_collected, 2),
        "total_outstanding": round(total_outstanding, 2),
        "collection_rate": round((total_collected / total_billed * 100.0) if total_billed > 0 else 0.0, 1),
        "paid_invoices": paid_count,
        "unpaid_invoices": unpaid_count,
        "partial_invoices": partial_count,
        "total_invoices": len(invoices),
    }
