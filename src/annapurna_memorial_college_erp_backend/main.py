import logging
from contextlib import asynccontextmanager
from pathlib import Path
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
    fees,
    notices,
    study_materials,
    audit,
    seed,
)

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("erp.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")
    await DatabaseManager.connect_to_mongo()
    yield
    logger.info("Shutting down ERP backend...")
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
app.include_router(fees.router, prefix=settings.API_V1_STR)
app.include_router(notices.router, prefix=settings.API_V1_STR)
app.include_router(study_materials.router, prefix=settings.API_V1_STR)
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
