import logging

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document, DocumentStatus
from app.services.storage_service import upload_file
from app.workers.tasks import process_uploaded_file


router = APIRouter(prefix="/sources", tags=["sources"])
logger = logging.getLogger(__name__)

@router.post("/upload")
async def upload_file_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    filename = file.filename or "uploaded.pdf"
    content_type = file.content_type or "application/octet-stream"

    if content_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hiện tại hệ thống chỉ hỗ trợ upload file PDF.",
        )

    try:
        reader = PdfReader(file.file)
        page_count = len(reader.pages)
    except (PdfReadError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File PDF không hợp lệ hoặc không đọc được.",
        ) from exc

    try:
        object_key = upload_file(file.file, filename)
    except (BotoCoreError, ClientError, OSError) as exc:
        logger.exception("Failed to upload source to object storage")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể lưu file vào storage. Kiểm tra MinIO/S3 rồi thử lại.",
        ) from exc

    document = Document(
        owner_id=current_user.id,
        filename=filename,
        page_count=page_count,
        file_type=content_type,
        storage_path=object_key,
        status=DocumentStatus.PROCESSING,
    )
    db.add(document)
    db.commit()
    db.refresh(document)


    task_id = None
    try:
        task = process_uploaded_file.delay(document.id)
        task_id = task.id
    except KombuError:
        logger.exception("Failed to enqueue source processing task")

    return {
        "document_id": document.id,
        "object_key": object_key,
        "name": document.filename,
        "meta": f"{document.page_count} trang",
        "type": document.file_type,
        "status": document.status.value,
        "checked": True,
    }

@router.get("/")
async def get_file(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    sources = (db.query(Document)
                .filter(Document.owner_id == current_user.id)
                .all()
    )

    result = []

    if len(sources) == 0:
        return []
    
    for s in sources:
        result.append({
            "document_id": s.id,
            "object_key": s.storage_path,
            "name": s.filename,
            "meta": f"{s.page_count} trang",
            "type": s.file_type,
            "status": s.status.value,
            "checked": True
        })

    return result
    
