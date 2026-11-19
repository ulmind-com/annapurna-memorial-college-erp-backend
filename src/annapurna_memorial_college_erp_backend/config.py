import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Annapurna Memorial College of Education ERP"
    COLLEGE_LEGAL_NAME: str = "Annapurna Memorial College of Education"
    COLLEGE_TAGLINE: str = "Excellence in Teacher Education & Higher Learning"
    COLLEGE_CODE: str = "AMCE-KASHINAGAR"
    COLLEGE_ADDRESS: str = "Kashinagar, South 24 Parganas, West Bengal 743349"
    COLLEGE_AFFILIATION: str = "Affiliated to BSAEU (WBUTTEPA) & Recognized by NCTE"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "production"

    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8000",
        "*",
    ]

    # Database
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "annapurna_erp_db"

    # Security & JWT
    JWT_SECRET_KEY: str = "annapurna-memorial-college-super-secret-jwt-key-2026-production-grade"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Third Party: Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    CLOUDINARY_FOLDER: str = "annapurna_college_erp"

    # Third Party: Resend Email
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "Annapurna College <notifications@annapurnacollege.org>"

    # Third Party: Firebase Cloud Messaging
    FIREBASE_CREDENTIALS_PATH: str = ""

    # Superadmin Default
    DEFAULT_ADMIN_EMAIL: str = "admin@annapurnacollege.edu.in"
    DEFAULT_ADMIN_PASSWORD: str = "Admin@Amce2024#"
    DEFAULT_ADMIN_NAME: str = "Dr. Arnab Senapati, Principal"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
