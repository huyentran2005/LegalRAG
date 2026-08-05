import logging
from io import BytesIO
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError
import httpx
from fastapi import APIRouter, UploadFile, File, Depends, Form, HTTPException, Query, status
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document, DocumentStatus
from app.models.chat_session import ChatSession
from app.services.storage_service import upload_file
from app.workers.tasks import process_uploaded_file


router = APIRouter(prefix="/sources", tags=["sources"])
logger = logging.getLogger(__name__)


def _validate_session(session_id: int | None, db: Session, user_id: int) -> int | None:
    if session_id is None:
        return None
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return session_id


def _source_payload(document: Document, checked: bool = True) -> dict:
    return {
        "document_id": document.id,
        "session_id": document.session_id,
        "object_key": document.storage_path,
        "name": document.filename,
        "meta": f"{document.page_count} trang",
        "type": document.file_type,
        "status": document.status.value,
        "checked": checked,
    }

@router.post("/upload")
async def upload_file_endpoint(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    sessionId: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session_id = _validate_session(sessionId, db, current_user.id)

    if not file and not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn cần chọn file PDF hoặc nhập link PDF.",
        )

    if file and url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ upload một nguồn mỗi lần: file hoặc link.",
        )

    if url:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Link tài liệu phải bắt đầu bằng http hoặc https.",
            )
        try:
            response = httpx.get(url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không tải được tài liệu từ link này.",
            ) from exc

        filename = parsed.path.rsplit("/", 1)[-1] or "linked-document.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        content_type = response.headers.get("content-type", "application/pdf").split(";")[0]
        file_obj = BytesIO(response.content)
    else:
        filename = file.filename or "uploaded.pdf"  # type: ignore[union-attr]
        content_type = file.content_type or "application/octet-stream"  # type: ignore[union-attr]
        file_obj = file.file  # type: ignore[union-attr]

    if content_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hiện tại hệ thống chỉ hỗ trợ upload file PDF.",
        )

    try:
        reader = PdfReader(file_obj)
        page_count = len(reader.pages)
    except (PdfReadError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File PDF không hợp lệ hoặc không đọc được.",
        ) from exc

    try:
        object_key = upload_file(file_obj, filename)
    except (BotoCoreError, ClientError, OSError) as exc:
        logger.exception("Failed to upload source to object storage")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể lưu file vào storage. Kiểm tra MinIO/S3 rồi thử lại.",
        ) from exc

    document = Document(
        owner_id=current_user.id,
        session_id=session_id,
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

    return _source_payload(document)

@router.get("/")
async def get_file(
    sessionId: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(Document).filter(Document.owner_id == current_user.id)
    if sessionId is not None:
        _validate_session(sessionId, db, current_user.id)
        query = query.filter(Document.session_id == sessionId)

    sources = (query
                .order_by(Document.created_at.desc())
                .all()
    )

    result = []

    if len(sources) == 0:
        return []
    
    for s in sources:
        result.append(_source_payload(s))

    return result
    
