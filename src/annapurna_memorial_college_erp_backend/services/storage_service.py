import os
import uuid
import base64
import logging
from pathlib import Path
from typing import Optional
from annapurna_memorial_college_erp_backend.config import settings

logger = logging.getLogger("erp.storage")

# Ensure local fallback directory exists
LOCAL_UPLOAD_DIR = Path("uploads")
LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class StorageService:
    def __init__(self):
        self.cloudinary_configured = False
        if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
            try:
                import cloudinary
                import cloudinary.uploader
                cloudinary.config(
                    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
                    api_key=settings.CLOUDINARY_API_KEY,
                    api_secret=settings.CLOUDINARY_API_SECRET,
                    secure=True
                )
                self.cloudinary_configured = True
                logger.info("Cloudinary storage provider initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize Cloudinary: {e}. Using local storage fallback.")

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        folder: Optional[str] = None,
        resource_type: str = "auto"
    ) -> str:
        """
        Uploads file to Cloudinary if configured; otherwise saves to local static uploads
        and returns local or data URI fallback.
        """
        folder_name = folder or settings.CLOUDINARY_FOLDER
        unique_name = f"{uuid.uuid4().hex[:12]}_{filename}"

        if self.cloudinary_configured:
            try:
                import cloudinary.uploader
                upload_res = cloudinary.uploader.upload(
                    file_bytes,
                    public_id=f"{folder_name}/{unique_name}",
                    resource_type=resource_type
                )
                secure_url = upload_res.get("secure_url")
                logger.info(f"File uploaded to Cloudinary: {secure_url}")
                return secure_url
            except Exception as e:
                logger.warning(f"Cloudinary upload failed ({e}). Falling back to local storage.")

        # Local filesystem fallback
        destination = LOCAL_UPLOAD_DIR / unique_name
        with open(destination, "wb") as f:
            f.write(file_bytes)

        fallback_url = f"/uploads/{unique_name}"
        logger.info(f"File saved to local storage: {fallback_url}")
        return fallback_url


storage_service = StorageService()
