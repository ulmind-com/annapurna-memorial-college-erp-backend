import logging
from typing import List, Optional, Dict, Any
from annapurna_memorial_college_erp_backend.config import settings

logger = logging.getLogger("erp.notifications")


class NotificationService:
    def __init__(self):
        self.firebase_app = None
        if settings.FIREBASE_CREDENTIALS_PATH:
            try:
                import firebase_admin
                from firebase_admin import credentials
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                self.firebase_app = firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin FCM initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize Firebase Admin: {e}. Fallback enabled.")

    async def send_push_notification(
        self,
        title: str,
        body: str,
        topic: Optional[str] = None,
        tokens: Optional[List[str]] = None,
        data: Optional[Dict[str, str]] = None
    ) -> bool:
        if self.firebase_app and (tokens or topic):
            try:
                from firebase_admin import messaging
                notification = messaging.Notification(title=title, body=body)
                if topic:
                    message = messaging.Message(
                        notification=notification,
                        data=data or {},
                        topic=topic
                    )
                    response = messaging.send(message)
                    logger.info(f"FCM push notification sent to topic '{topic}': {response}")
                    return True
                elif tokens:
                    multicast_msg = messaging.MulticastMessage(
                        notification=notification,
                        data=data or {},
                        tokens=tokens
                    )
                    batch_resp = messaging.send_multicast(multicast_msg)
                    logger.info(f"FCM multicast sent to {len(tokens)} tokens. Success count: {batch_resp.success_count}")
                    return True
            except Exception as e:
                logger.warning(f"Firebase FCM dispatch error: {e}. Falling back to simulation.")

        # Graceful fallback simulation
        logger.info(
            f"[MOCK PUSH NOTIFICATION] Target: {topic or tokens} | Title: '{title}' | Body: '{body}'"
        )
        return True


notification_service = NotificationService()
