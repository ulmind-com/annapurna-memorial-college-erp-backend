import logging
from typing import List, Optional
from annapurna_memorial_college_erp_backend.config import settings

logger = logging.getLogger("erp.email")


class EmailService:
    def __init__(self):
        self.resend_configured = False
        if settings.RESEND_API_KEY:
            try:
                import resend
                resend.api_key = settings.RESEND_API_KEY
                self.resend_configured = True
                logger.info("Resend email provider initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize Resend: {e}")

    async def send_email(
        self,
        to_emails: List[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        if self.resend_configured:
            try:
                import resend
                params = {
                    "from": settings.RESEND_FROM_EMAIL,
                    "to": to_emails,
                    "subject": subject,
                    "html": html_content,
                }
                if text_content:
                    params["text"] = text_content
                response = resend.Emails.send(params)
                logger.info(f"Email sent via Resend to {to_emails}. ID: {response.get('id')}")
                return True
            except Exception as e:
                logger.warning(f"Resend email dispatch error: {e}. Fallback to simulated log.")

        # Resilient fallback: log email dispatch details
        logger.info(
            f"[MOCK EMAIL DISPATCH] To: {to_emails} | Subject: '{subject}' | Body preview: {html_content[:120]}..."
        )
        return True

    async def send_password_reset_email(self, to_email: str, reset_token: str) -> bool:
        subject = f"Password Reset Request - {settings.PROJECT_NAME}"
        reset_link = f"http://localhost:5173/reset-password?token={reset_token}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
            <h2 style="color: #1e3a8a;">{settings.COLLEGE_LEGAL_NAME}</h2>
            <p>You requested a password reset for your college ERP account.</p>
            <p style="margin: 24px 0;">
                <a href="{reset_link}" style="background-color: #1e40af; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                    Reset Your Password
                </a>
            </p>
            <p style="color: #64748b; font-size: 13px;">If you did not request this, please ignore this email. This link is valid for 1 hour.</p>
        </div>
        """
        return await self.send_email([to_email], subject, html)

    async def send_marksheet_publication_notice(self, to_email: str, student_name: str, exam_title: str) -> bool:
        subject = f"Official Marksheet Published: {exam_title}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
            <h2 style="color: #059669;">Marksheet Published Notification</h2>
            <p>Dear {student_name},</p>
            <p>Your official marksheet for <strong>{exam_title}</strong> has been verified, approved, and published by the examination authority of <strong>{settings.COLLEGE_LEGAL_NAME}</strong>.</p>
            <p>Please log in to your Student Portal to view your statement of marks and download the digitally signed PDF.</p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
            <p style="color: #64748b; font-size: 12px;">Office of the Controller of Examinations, {settings.COLLEGE_LEGAL_NAME}</p>
        </div>
        """
        return await self.send_email([to_email], subject, html)


email_service = EmailService()
