from sqlalchemy.orm import Session
from urllib.parse import urlparse
from fastapi import  HTTPException, status


from app.models.chat_session import ChatSession

PDF_CONTENT_TYPES = {"application/pdf"}
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm"}

def _validate_session(session_id: int | None, db: Session, user_id: int) -> int | None:
    if session_id is None:
        return None
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return session_id


def _extension_from_filename(filename: str) -> str:
    lowered = filename.lower()
    for extension in SUPPORTED_EXTENSIONS:
        if lowered.endswith(extension):
            return extension
    return ""


def _filename_from_url(url: str, content_type: str) -> str:
    parsed = urlparse(url)
    filename = parsed.path.rsplit("/", 1)[-1] or "linked-document"
    if _extension_from_filename(filename):
        return filename
    if content_type in HTML_CONTENT_TYPES:
        return f"{filename}.html"
    if content_type in DOCX_CONTENT_TYPES:
        return f"{filename}.docx"
    return f"{filename}.pdf"


def _is_supported_source(filename: str, content_type: str) -> bool:
    extension = _extension_from_filename(filename)
    return (
        extension in SUPPORTED_EXTENSIONS
        or content_type in PDF_CONTENT_TYPES
        or content_type in HTML_CONTENT_TYPES
        or content_type in DOCX_CONTENT_TYPES
    )