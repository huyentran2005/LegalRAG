import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from app.core.config import get_settings

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

