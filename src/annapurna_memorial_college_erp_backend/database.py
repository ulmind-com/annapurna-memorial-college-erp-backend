import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from annapurna_memorial_college_erp_backend.config import settings

logger = logging.getLogger("erp.database")


class DatabaseManager:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect_to_mongo(cls):
        try:
            logger.info(f"Connecting to MongoDB at {settings.MONGODB_URI}...")
            cls.client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )
            cls.db = cls.client[settings.MONGODB_DB_NAME]
            # Ping database
            await cls.client.admin.command("ping")
            logger.info(f"Successfully connected to MongoDB: {settings.MONGODB_DB_NAME}")
            await cls.init_indexes()
        except Exception as e:
            logger.warning(f"Could not establish live MongoDB connection ({e}). Operating in memory/resilient mode.")

    @classmethod
    async def close_mongo_connection(cls):
        if cls.client:
            logger.info("Closing MongoDB connection...")
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB connection closed.")

    @classmethod
    async def init_indexes(cls):
        if cls.db is None:
            return
        try:
            # Users
            await cls.db.users.create_index("email", unique=True)
            await cls.db.users.create_index("username", unique=True, sparse=True)
            await cls.db.users.create_index("role")

            # Students
            await cls.db.students.create_index("roll_number", unique=True)
            await cls.db.students.create_index("registration_number", unique=True, sparse=True)
            await cls.db.students.create_index("course_code")
            await cls.db.students.create_index("academic_session")
            await cls.db.students.create_index([("course_code", 1), ("semester", 1)])

            # Faculty
            await cls.db.faculty.create_index("employee_id", unique=True)
            await cls.db.faculty.create_index("email", unique=True)
            await cls.db.faculty.create_index("department")

            # Courses & Subjects
            await cls.db.courses.create_index("code", unique=True)
            await cls.db.subjects.create_index("code", unique=True)
            await cls.db.subjects.create_index("course_code")

            # Attendance
            await cls.db.attendance.create_index([("date", 1), ("course_code", 1), ("semester", 1), ("subject_code", 1)])
            await cls.db.attendance.create_index("student_id")

            # Examinations & Marksheets
            await cls.db.examinations.create_index("code", unique=True)
            await cls.db.marksheets.create_index([("student_id", 1), ("exam_id", 1)], unique=True)
            await cls.db.marksheets.create_index("status")
            await cls.db.marksheets.create_index("course_code")

            # Fees
            await cls.db.fee_structures.create_index([("course_code", 1), ("academic_session", 1), ("semester", 1)])
            await cls.db.invoices.create_index("invoice_number", unique=True)
            await cls.db.invoices.create_index("student_id")
            await cls.db.payments.create_index("transaction_id", unique=True)

            # Notices
            await cls.db.notices.create_index([("created_at", -1)])
            await cls.db.notices.create_index("target_audience")

            # Mobile Device Tokens
            await cls.db.device_tokens.create_index("fcm_token", unique=True)
            await cls.db.device_tokens.create_index("user_id")

            # Audit Logs
            await cls.db.audit_logs.create_index([("timestamp", -1)])

            logger.info("MongoDB indexes verified and ensured.")
        except Exception as e:
            logger.warning(f"Error initializing indexes: {e}")

    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        if cls.db is None:
            # Create lazy client if not yet connected
            cls.client = AsyncIOMotorClient(settings.MONGODB_URI)
            cls.db = cls.client[settings.MONGODB_DB_NAME]
        return cls.db


async def get_db() -> AsyncIOMotorDatabase:
    return DatabaseManager.get_database()
