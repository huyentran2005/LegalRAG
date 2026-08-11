from fastapi import HTTPException,status
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.source.extractor import _extract_docx_links, _extract_html_links, _extract_pdf_links
from app.services.source.utils import _extension_from_filename


PDF_CONTENT_TYPES = {"application/pdf"}
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm"}

def _inspect_source(file_obj, filename: str, content_type: str) -> tuple[int, list[str]]:
    extension = _extension_from_filename(filename)
    if content_type in PDF_CONTENT_TYPES or extension == ".pdf":
        try:
            file_obj.seek(0)
            reader = PdfReader(file_obj)
            page_count = len(reader.pages)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return page_count, _extract_pdf_links(reader, text)
        except (PdfReadError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File PDF không hợp lệ hoặc không đọc được.",
            ) from exc

    if content_type in DOCX_CONTENT_TYPES or extension == ".docx":
        try:
            return _extract_docx_links(file_obj)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File DOCX không hợp lệ hoặc không đọc được.",
            ) from exc

    if content_type in HTML_CONTENT_TYPES or extension in {".html", ".htm"}:
        try:
            file_obj.seek(0)
            raw = file_obj.read()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            return 1, _extract_html_links(str(raw))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File HTML không hợp lệ hoặc không đọc được.",
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Hiện tại hệ thống chỉ hỗ trợ upload file PDF, DOCX hoặc HTML.",
    )
