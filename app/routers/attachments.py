import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_scope, CurrentUser
from app.database import get_db
from app.models import Complaint, ComplaintAttachment

router = APIRouter(tags=["attachments"])

UPLOAD_DIR = "uploads"
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


async def _get_owned_complaint(db: AsyncSession, complaint_id: UUID, agency_code: str) -> Complaint:
    result = await db.execute(
        select(Complaint).where(Complaint.id == complaint_id, Complaint.agency == agency_code)
    )
    complaint = result.scalar_one_or_none()
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@router.post("/complaints/{complaint_id}/attachments", status_code=201)
async def upload_attachment(
    complaint_id: UUID,
    file: UploadFile,
    user: CurrentUser = Depends(require_scope("complaints:write")),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported content type '{file.content_type}'. Allowed: image/png, image/jpeg, application/pdf",
        )

    await _get_owned_complaint(db, complaint_id, user.agency_code)

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_filename = os.path.basename(file.filename)
    storage_path = os.path.join(UPLOAD_DIR, f"{complaint_id}_{safe_filename}")

    size = 0
    with open(storage_path, "wb") as out_file:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE_BYTES:
                out_file.close()
                os.remove(storage_path)
                raise HTTPException(status_code=413, detail="File too large (max 10MB)")
            out_file.write(chunk)

    attachment = ComplaintAttachment(
        complaint_id=complaint_id,
        filename=safe_filename,
        content_type=file.content_type,
        file_size_bytes=size,
        storage_path=storage_path,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return {
        "id": str(attachment.id),
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "file_size_bytes": attachment.file_size_bytes,
    }


@router.get("/complaints/{complaint_id}/attachments")
async def list_attachments(
    complaint_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_complaint(db, complaint_id, user.agency_code)

    result = await db.execute(
        select(ComplaintAttachment).where(ComplaintAttachment.complaint_id == complaint_id)
    )
    attachments = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "filename": a.filename,
            "content_type": a.content_type,
            "file_size_bytes": a.file_size_bytes,
            "uploaded_at": a.uploaded_at,
        }
        for a in attachments
    ]


@router.get("/complaints/{complaint_id}/attachment/{attachment_id}/download")
async def download_attachment(
    complaint_id: UUID,
    attachment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_complaint(db, complaint_id, user.agency_code)

    result = await db.execute(
        select(ComplaintAttachment).where(
            ComplaintAttachment.id == attachment_id,
            ComplaintAttachment.complaint_id == complaint_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if attachment is None or not os.path.exists(attachment.storage_path):
        raise HTTPException(status_code=404, detail="Attachment not found")

    return FileResponse(
        path=attachment.storage_path,
        media_type=attachment.content_type,
        filename=attachment.filename,
    )