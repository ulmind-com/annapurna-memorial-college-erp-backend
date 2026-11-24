import io
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
from fastapi import HTTPException, status
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from annapurna_memorial_college_erp_backend.config import settings
from annapurna_memorial_college_erp_backend.schemas.examination import (
    MarksheetStatus,
    SubjectScoreInput,
    SubjectScoreOutput,
    AuditTrailEntry,
)


class MarksheetService:
    @staticmethod
    def calculate_grade(percentage: float) -> Tuple[float, str]:
        """
        NCTE / BSAEU Standard Grading Scale
        """
        if percentage >= 90.0:
            return 10.0, "O"  # Outstanding
        elif percentage >= 80.0:
            return 9.0, "A+"  # Excellent
        elif percentage >= 70.0:
            return 8.0, "A"  # Very Good
        elif percentage >= 60.0:
            return 7.0, "B+"  # Good
        elif percentage >= 55.0:
            return 6.0, "B"  # Above Average
        elif percentage >= 50.0:
            return 5.5, "C"  # Average
        elif percentage >= 40.0:
            return 5.0, "P"  # Pass
        else:
            return 0.0, "F"  # Fail

    @staticmethod
    def determine_result_status(overall_percentage: float, any_fail: bool) -> str:
        if any_fail or overall_percentage < 40.0:
            return "FAIL"
        elif overall_percentage >= 75.0:
            return "FIRST CLASS WITH DISTINCTION"
        elif overall_percentage >= 60.0:
            return "FIRST CLASS"
        elif overall_percentage >= 50.0:
            return "SECOND CLASS"
        else:
            return "PASS"

    @classmethod
    def process_subject_scores(
        cls, scores: List[SubjectScoreInput]
    ) -> Tuple[List[SubjectScoreOutput], float, float, float, float, str]:
        processed: List[SubjectScoreOutput] = []
        total_obtained = 0.0
        grand_max = 0.0
        total_credits = 0
        total_credit_points = 0.0
        any_failed = False

        for s in scores:
            tot = s.theory_obtained + s.practical_obtained
            max_m = s.max_theory + s.max_practical
            pct = (tot / max_m * 100.0) if max_m > 0 else 0.0
            gp, letter = cls.calculate_grade(pct)

            if letter == "F":
                any_failed = True

            total_obtained += tot
            grand_max += max_m
            total_credits += s.credits
            total_credit_points += s.credits * gp

            processed.append(
                SubjectScoreOutput(
                    subject_code=s.subject_code,
                    subject_title=s.subject_title,
                    credits=s.credits,
                    theory_obtained=s.theory_obtained,
                    practical_obtained=s.practical_obtained,
                    max_theory=s.max_theory,
                    max_practical=s.max_practical,
                    remarks=s.remarks,
                    total_obtained=tot,
                    max_marks=max_m,
                    percentage=round(pct, 2),
                    grade_point=gp,
                    letter_grade=letter,
                )
            )

        overall_pct = (total_obtained / grand_max * 100.0) if grand_max > 0 else 0.0
        sgpa = (total_credit_points / total_credits) if total_credits > 0 else 0.0
        result_status = cls.determine_result_status(overall_pct, any_failed)

        return (
            processed,
            round(total_obtained, 2),
            round(grand_max, 2),
            round(overall_pct, 2),
            round(sgpa, 2),
            result_status,
        )

    @staticmethod
    def generate_verification_hash(student_id: str, exam_id: str, sgpa: float) -> str:
        salt = "AMC_SABED_SECURE_VERIFICATION_2026"
        payload = f"{student_id}:{exam_id}:{sgpa}:{salt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24].upper()

    @classmethod
    def validate_transition(
        cls,
        current_status: MarksheetStatus,
        action: str,
        user_role: str,
        remarks: str = "",
    ) -> MarksheetStatus:
        """
        State Machine for Marksheet Approval Workflow
        DRAFT -> SUBMITTED_BY_FACULTY -> DEPARTMENT_VERIFIED -> ADMIN_APPROVED -> PUBLISHED
        """
        action = action.upper()

        if action == "REJECT":
            if not remarks:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Rejection reason / remarks are required when rejecting a marksheet.",
                )
            return MarksheetStatus.REJECTED

        if action == "SUBMIT":
            if current_status not in [MarksheetStatus.DRAFT, MarksheetStatus.REJECTED]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot submit marksheet from status '{current_status}'.",
                )
            return MarksheetStatus.SUBMITTED_BY_FACULTY

        if action == "VERIFY":
            if current_status != MarksheetStatus.SUBMITTED_BY_FACULTY:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot department-verify marksheet from status '{current_status}'. Must be SUBMITTED_BY_FACULTY.",
                )
            if user_role not in ["ADMIN", "SUPER_ADMIN"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Department verification requires Admin or Academic Coordinator role.",
                )
            return MarksheetStatus.DEPARTMENT_VERIFIED

        if action == "APPROVE":
            if current_status != MarksheetStatus.DEPARTMENT_VERIFIED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot approve marksheet from status '{current_status}'. Must be DEPARTMENT_VERIFIED.",
                )
            if user_role not in ["ADMIN", "SUPER_ADMIN"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Final approval requires Principal or Super Admin role.",
                )
            return MarksheetStatus.ADMIN_APPROVED

        if action == "PUBLISH":
            if current_status != MarksheetStatus.ADMIN_APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot publish marksheet from status '{current_status}'. Must be ADMIN_APPROVED first.",
                )
            if user_role not in ["ADMIN", "SUPER_ADMIN"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Publishing requires Super Admin or Principal role.",
                )
            return MarksheetStatus.PUBLISHED

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported workflow action '{action}'.",
        )

    @classmethod
    def generate_pdf(cls, marksheet_data: Dict[str, Any]) -> bytes:
        """
        Generates an ultra-pro, official grade sheet / marksheet PDF using ReportLab
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CollegeTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            alignment=1,  # Center
            textColor=colors.HexColor("#1e3a8a"),
        )
        sub_style = ParagraphStyle(
            "CollegeSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=colors.HexColor("#475569"),
        )
        exam_style = ParagraphStyle(
            "ExamHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            alignment=1,
            textColor=colors.HexColor("#0f172a"),
        )
        cell_style = ParagraphStyle(
            "CellText",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
        )
        cell_bold = ParagraphStyle(
            "CellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
        )

        elements = []

        # Header
        elements.append(Paragraph(settings.COLLEGE_LEGAL_NAME.upper(), title_style))
        elements.append(Paragraph(settings.COLLEGE_AFFILIATION, sub_style))
        elements.append(Paragraph(settings.COLLEGE_ADDRESS, sub_style))
        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1e3a8a"), spaceAfter=10))

        # Title
        tpl = marksheet_data.get("_template") or {}
        elements.append(Paragraph(tpl.get("format_title") or "OFFICIAL STATEMENT OF MARKS & GRADES", exam_style))
        elements.append(Paragraph(f"<b>Examination:</b> {marksheet_data.get('exam_title', 'Semester Examination')}", sub_style))
        elements.append(Spacer(1, 12))

        # Student Details Box
        student_info = [
            [
                Paragraph(f"<b>Student Name:</b> {marksheet_data.get('student_name')}", cell_style),
                Paragraph(f"<b>Roll Number:</b> {marksheet_data.get('roll_number')}", cell_style),
            ],
            [
                Paragraph(f"<b>Course / Program:</b> {marksheet_data.get('course_name', 'B.Ed.')}", cell_style),
                Paragraph(f"<b>Registration No:</b> {marksheet_data.get('registration_number', 'N/A')}", cell_style),
            ],
            [
                Paragraph(f"<b>Academic Session:</b> {marksheet_data.get('academic_session')}", cell_style),
                Paragraph(f"<b>Semester:</b> Semester {marksheet_data.get('semester')}", cell_style),
            ],
            [
                Paragraph(f"<b>Verification Hash:</b> <font color='#1e40af'>{marksheet_data.get('qr_code_hash', 'VERIFIED')}</font>", cell_style),
                Paragraph(f"<b>Status:</b> <b>{marksheet_data.get('status')}</b>", cell_style),
            ],
        ]
        info_table = Table(student_info, colWidths=[270, 250])
        info_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elements.append(info_table)
        elements.append(Spacer(1, 14))

        # Marks Breakdown Table
        headers = [
            Paragraph("<b>Subject Code</b>", cell_bold),
            Paragraph("<b>Subject Title</b>", cell_bold),
            Paragraph("<b>Credits</b>", cell_bold),
            Paragraph("<b>Theory (Max)</b>", cell_bold),
            Paragraph("<b>Prac (Max)</b>", cell_bold),
            Paragraph("<b>Total</b>", cell_bold),
            Paragraph("<b>Grade Pt</b>", cell_bold),
            Paragraph("<b>Grade</b>", cell_bold),
        ]
        table_rows = [headers]

        for s in marksheet_data.get("subject_scores", []):
            table_rows.append([
                Paragraph(s.get("subject_code", ""), cell_style),
                Paragraph(s.get("subject_title", ""), cell_style),
                Paragraph(str(s.get("credits", 4)), cell_style),
                Paragraph(f"{s.get('theory_obtained', 0)} ({s.get('max_theory', 70)})", cell_style),
                Paragraph(f"{s.get('practical_obtained', 0)} ({s.get('max_practical', 30)})", cell_style),
                Paragraph(f"<b>{s.get('total_obtained', 0)}</b> / {s.get('max_marks', 100)}", cell_style),
                Paragraph(str(s.get("grade_point", 0.0)), cell_style),
                Paragraph(f"<b>{s.get('letter_grade', 'P')}</b>", cell_style),
            ])

        scores_table = Table(table_rows, colWidths=[70, 160, 40, 65, 65, 55, 45, 40])
        scores_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        elements.append(scores_table)
        elements.append(Spacer(1, 14))

        # Summary Statistics Table
        summary_rows = [
            [
                Paragraph("<b>Total Marks Obtained</b>", cell_bold),
                Paragraph(f"{marksheet_data.get('total_marks_obtained')} / {marksheet_data.get('grand_max_marks')}", cell_style),
                Paragraph("<b>Overall Percentage</b>", cell_bold),
                Paragraph(f"{marksheet_data.get('overall_percentage')}%", cell_style),
            ],
            [
                Paragraph("<b>Semester GPA (SGPA)</b>", cell_bold),
                Paragraph(f"<font size='10' color='#1e40af'><b>{marksheet_data.get('sgpa')}</b></font>", cell_style),
                Paragraph("<b>Final Classification</b>", cell_bold),
                Paragraph(f"<b>{marksheet_data.get('result_status')}</b>", cell_style),
            ]
        ]
        summary_table = Table(summary_rows, colWidths=[130, 130, 130, 130])
        summary_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
                ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#3b82f6")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        elements.append(summary_table)
        elements.append(Spacer(1, 30))

        # Signatures
        sig_data = [
            [
                Paragraph("Verified By<br/><b>Academic Coordinator</b>", cell_style),
                Paragraph(f"Approved By<br/><b>{tpl.get('principal_signature_title') or 'Principal / Director'}</b>", cell_style),
                Paragraph(f"Digitally Certified By<br/><b>{tpl.get('controller_signature_title') or 'Controller of Examinations'}</b>", cell_style),
            ]
        ]
        sig_table = Table(sig_data, colWidths=[170, 170, 180])
        sig_table.setStyle(
            TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.75, colors.HexColor("#64748b")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        elements.append(sig_table)

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()


marksheet_service = MarksheetService()
