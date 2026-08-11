import uuid
import re
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from io import BytesIO
from urllib.parse import parse_qs, urlparse
from botocore.exceptions import BotoCoreError, ClientError
import httpx
from fastapi import  HTTPException
from redis.client import logger
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document, DocumentStatus
from app.services.source.inspector import _inspect_source
from app.services.source.utils import _filename_from_url, _is_supported_source


settings = get_settings()

_config = Config(
    connect_timeout=3,
    read_timeout=5,
    retries={"max_attempts": 2},
)

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            use_ssl=settings.s3_secure,
            config=_config,
        )
    return _client

TMP_DIR = Path(settings.upload_temp_dir)
TMP_DIR.mkdir(parents=True, exist_ok=True)


def ensure_bucket_exists() -> None:
    try:
        client = _get_client()
        client.head_bucket(Bucket=settings.s3_bucket_name)
    except ClientError:
        try:
            client = _get_client()
            client.create_bucket(Bucket=settings.s3_bucket_name)
        except Exception:
            pass

def upload_file(file_obj, filename: str | None) -> str:
    object_key = f"{uuid.uuid4()}_{filename}"
    file_obj.seek(0)
    client = _get_client()
    client.upload_fileobj(file_obj, settings.s3_bucket_name, object_key)
    return object_key


def download_to_temp(object_key: str, tmp_dir: str | Path = TMP_DIR) -> str:
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    local_path = tmp_dir / object_key
    client = _get_client()
    client.download_file(settings.s3_bucket_name, object_key, str(local_path))
    return str(local_path)


def cleanup_temp_file(path: str) -> None:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass




def _create_document_from_file_obj(
    db: Session,
    current_user_id: int,
    session_id: int | None,
    file_obj,
    filename: str,
    content_type: str,
    page_count: int,
) -> Document:
    object_key = upload_file(file_obj, filename)
    document = Document(
        owner_id=current_user_id,
        session_id=session_id,
        filename=filename,
        page_count=page_count,
        file_type=content_type,
        storage_path=object_key,
        status=DocumentStatus.PROCESSING,
    )
    db.add(document)
    db.flush()
    return document


def _download_url_source(url: str) -> tuple[BytesIO, str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Unsupported URL scheme")
    if "drive.google.com" in parsed.netloc.lower():
        file_id = None
        path_match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
        if path_match:
            file_id = path_match.group(1)
        else:
            qs = parse_qs(parsed.query)
            file_id = (qs.get("id") or [None])[0]
        if file_id:
            url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = httpx.get(url, follow_redirects=True, timeout=30.0)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "application/pdf").split(";")[0]
    filename = _filename_from_url(url, content_type)
    return BytesIO(response.content), filename, content_type


def _create_linked_documents(
    db: Session,
    current_user_id: int,
    session_id: int | None,
    links: list[str],
) -> list[Document]:
    documents = []
    for link in links:
        try:
            file_obj, filename, content_type = _download_url_source(link)
            if not _is_supported_source(filename, content_type):
                logger.info("Skipping unsupported linked source url=%s content_type=%s", link, content_type)
                continue
            page_count, _nested_links = _inspect_source(file_obj, filename, content_type)
            document = _create_document_from_file_obj(
                db=db,
                current_user_id=current_user_id,
                session_id=session_id,
                file_obj=file_obj,
                filename=filename,
                content_type=content_type,
                page_count=page_count,
            )
            documents.append(document)
        except (httpx.HTTPError, ValueError, HTTPException, BotoCoreError, ClientError, OSError):
            logger.exception("Failed to import linked source url=%s", link)
    return documents