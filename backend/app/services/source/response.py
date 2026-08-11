from app.models.document import Document


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


def _upload_response(document: Document, linked_documents: list[Document] | None = None) -> dict:
    payload = _source_payload(document)
    payload["linkedSources"] = [
        _source_payload(linked_document)
        for linked_document in (linked_documents or [])
    ]
    return payload
