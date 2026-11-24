import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from annapurna_memorial_college_erp_backend.config import settings
from annapurna_memorial_college_erp_backend.database import DatabaseManager
from annapurna_memorial_college_erp_backend.routers import (
    health,
    auth,
    users,
    students,
    faculty,
    academics,
    attendance,
    examinations,
    leaves,
    feedback,
    notices,
    notifications,
    study_materials,
    assignments,
    audit,
    seed,
)

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("erp.main")


async def keep_alive_worker():
    """Periodically ping self public endpoint every 9 minutes so Render free instances never sleep."""
    await asyncio.sleep(45)
    while True:
        try:
            url = "https://annapurna-memorial-college-erp-adminpanel.onrender.com/health"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url)
                logger.info(f"Keep-alive self-ping: status {res.status_code}")
        except Exception as e:
            logger.debug(f"Keep-alive ping exception: {e}")
        await asyncio.sleep(540)  # 9 minutes (< 15 min Render idle timeout)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")
    await DatabaseManager.connect_to_mongo()
    ping_task = asyncio.create_task(keep_alive_worker())
    yield
    logger.info("Shutting down ERP backend...")
    ping_task.cancel()
    await DatabaseManager.close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=f"""
    **{settings.COLLEGE_LEGAL_NAME}**
    *{settings.COLLEGE_TAGLINE}*

    Comprehensive Enterprise Resource Planning (ERP) REST API backend.
    Includes RBAC, Multi-stage Marksheet Approval Pipeline, Student Admissions, Faculty Management,
    Attendance, Fees, Digital Notices, and Study Materials.
    """,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve local uploads directory for fallbacks
uploads_path = Path("uploads")
uploads_path.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include Routers
app.include_router(health.router)
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(users.router, prefix=settings.API_V1_STR)
app.include_router(students.router, prefix=settings.API_V1_STR)
app.include_router(faculty.router, prefix=settings.API_V1_STR)
app.include_router(academics.router, prefix=settings.API_V1_STR)
app.include_router(attendance.router, prefix=settings.API_V1_STR)
app.include_router(examinations.router, prefix=settings.API_V1_STR)
app.include_router(leaves.router, prefix=settings.API_V1_STR)
app.include_router(feedback.router, prefix=settings.API_V1_STR)
app.include_router(notices.router, prefix=settings.API_V1_STR)
app.include_router(notifications.router, prefix=settings.API_V1_STR)
app.include_router(study_materials.router, prefix=settings.API_V1_STR)
app.include_router(assignments.router, prefix=settings.API_V1_STR)
app.include_router(audit.router, prefix=settings.API_V1_STR)
app.include_router(seed.router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {
        "institution": settings.COLLEGE_LEGAL_NAME,
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "api_v1": settings.API_V1_STR,
    }


def main():
    import uvicorn
    uvicorn.run(
        "annapurna_memorial_college_erp_backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
