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
                    batch_resp = messaging.send_each_for_multicast(multicast_msg)
                    logger.info(f"FCM multicast sent to {len(tokens)} tokens. Success count: {batch_resp.success_count}")
                    return True
            except Exception as e:
                logger.warning(f"Firebase FCM dispatch error: {e}. Falling back to simulation.")

        # Graceful fallback simulation
        logger.info(
            f"[MOCK PUSH NOTIFICATION] Target: {topic or tokens} | Title: '{title}' | Body: '{body}'"
        )
        return True

    async def notify_users(
        self,
        db,
        user_ids: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
    ) -> int:
        """Push to every registered device of the given users. Returns token count."""
        if not user_ids:
            return 0
        tokens = [
            t["fcm_token"]
            async for t in db.device_tokens.find({"user_id": {"$in": list(set(user_ids))}}, {"fcm_token": 1})
            if t.get("fcm_token")
        ]
        # FCM multicast limit is 500 tokens per call
        for i in range(0, len(tokens), 500):
            await self.send_push_notification(title=title, body=body, tokens=tokens[i:i + 500], data=data)
        if not tokens:
            logger.info(f"[PUSH] No registered devices for {len(user_ids)} user(s): '{title}'")
        return len(tokens)


notification_service = NotificationService()
