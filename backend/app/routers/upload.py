import logging
from botocore.exceptions import BotoCoreError, ClientError
import httpx
from fastapi import APIRouter, UploadFile, File, Depends, Form, HTTPException, Query, status
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session


from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document
from app.workers.tasks import process_uploaded_file
from app.services.source.inspector import _inspect_source
from app.services.source.storage_service import _create_document_from_file_obj, _create_linked_documents, _download_url_source
from app.services.source.utils import _is_supported_source, _validate_session
from app.services.source.response import _source_payload, _upload_response

router = APIRouter(prefix="/sources", tags=["sources"])
logger = logging.getLogger(__name__)





def _enqueue_document_processing(document_id: int) -> str | None:
    try:
        task = process_uploaded_file.delay(document_id)
        return task.id
    except KombuError:
        logger.exception("Failed to enqueue source processing task")
        return None


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
            detail="Bạn cần chọn file PDF/DOCX/HTML hoặc nhập link phù hợp.",
        )

    if file and url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ upload một nguồn mỗi lần: file hoặc link.",
        )

    if url:
        try:
            file_obj, filename, content_type = _download_url_source(url)
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không tải được tài liệu từ link này.",
            ) from exc
    else:
        filename = file.filename or "uploaded.pdf"  # type: ignore[union-attr]
        content_type = file.content_type or "application/octet-stream"  # type: ignore[union-attr]
        file_obj = file.file  # type: ignore[union-attr]

    if not _is_supported_source(filename, content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hiện tại hệ thống chỉ hỗ trợ upload file PDF, DOCX hoặc HTML.",
        )

    page_count, links = _inspect_source(file_obj, filename, content_type)

    try:
        document = _create_document_from_file_obj(
            db=db,
            current_user_id=current_user.id,
            session_id=session_id,
            file_obj=file_obj,
            filename=filename,
            content_type=content_type,
            page_count=page_count,
        )

        linked_documents = _create_linked_documents(
            db=db,
            current_user_id=current_user.id,
            session_id=session_id,
            links=links,
        )
        db.commit()
        db.refresh(document)
        for linked_document in linked_documents:
            db.refresh(linked_document)
    except (BotoCoreError, ClientError, OSError) as exc:
        db.rollback()
        logger.exception("Failed to upload source to object storage")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể lưu file vào storage. Kiểm tra MinIO/S3 rồi thử lại.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    _enqueue_document_processing(document.id)
    for linked_document in linked_documents:
        _enqueue_document_processing(linked_document.id)

    return _upload_response(document, linked_documents)


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
    
