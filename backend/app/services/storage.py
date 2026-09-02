"""Private evidence/report storage with a filesystem cache and optional Supabase object authority."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

settings = get_settings()

ALLOWED_EXTENSIONS = {
    ".txt": {"text/plain"}, ".eml": {"message/rfc822", "text/plain"}, ".csv": {"text/csv", "application/csv", "text/plain"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}, ".pdf": {"application/pdf"},
    ".png": {"image/png"}, ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"},
}


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    stored_name: str
    extension: str
    detected_mime: str
    byte_size: int
    sha256: str


def using_supabase_storage() -> bool:
    return settings.storage_backend == "supabase"


def _safe_storage_key(storage_key: str) -> str:
    path = PurePosixPath(storage_key)
    if not storage_key or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Private evidence object is not available")
    return path.as_posix()


def _remote_headers() -> dict[str, str]:
    if not settings.supabase_service_role_key:
        raise RuntimeError("Supabase private storage credentials are unavailable")
    key = settings.supabase_service_role_key.get_secret_value()
    return {"Authorization": f"Bearer {key}", "apikey": key}


def _object_url(storage_key: str) -> str:
    if not settings.supabase_url or not settings.supabase_storage_bucket:
        raise RuntimeError("Supabase private storage configuration is unavailable")
    return "/".join(
        [
            settings.supabase_url.rstrip("/"),
            "storage/v1/object",
            quote(settings.supabase_storage_bucket, safe=""),
            quote(_safe_storage_key(storage_key), safe="/"),
        ]
    )


def _remote_failure(action: str, exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Private evidence storage {action} is temporarily unavailable")


def _safe_extension(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Evidence filename is required")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported evidence file type")
    return extension


def detect_mime(prefix: bytes, extension: str) -> str:
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if prefix.startswith(b"PK\x03\x04") and extension == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if extension == ".eml" and (b"From:" in prefix or b"Subject:" in prefix):
        return "message/rfc822"
    if extension in {".txt", ".csv", ".eml"}:
        try:
            prefix.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Text evidence is not UTF-8 readable") from exc
        return "text/csv" if extension == ".csv" else "text/plain"
    raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="File signature does not match an accepted evidence type")


def source_category(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "_", value.lower()).strip("_")
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A valid source category is required")
    return cleaned[:64]


def _cache_path(storage_key: str, cache_root: Path) -> Path:
    return cache_root / ".remote-cache" / _safe_storage_key(storage_key)


def publish_private_file(source: Path, storage_key: str, *, content_type: str) -> None:
    """Store an immutable artifact in Supabase when configured; filesystem mode keeps its local source."""
    if not using_supabase_storage():
        return
    try:
        headers = _remote_headers() | {"Content-Type": content_type, "x-upsert": "false"}
        with httpx.Client(timeout=90.0, follow_redirects=False) as client:
            response = client.post(_object_url(storage_key), headers=headers, content=source.read_bytes())
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _remote_failure("upload", exc) from exc


def materialize_private_file(storage_key: str, *, cache_root: Path) -> Path:
    """Return a local immutable file path for parsers and FileResponse without exposing object-store URLs."""
    storage_key = _safe_storage_key(storage_key)
    if not using_supabase_storage():
        candidate = (cache_root / storage_key).resolve()
        root = cache_root.resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Private evidence object is not available")
        return candidate

    cached = _cache_path(storage_key, cache_root)
    if cached.is_file():
        return cached
    temporary = cached.with_name(f".{cached.name}.{uuid4().hex}.part")
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=90.0, follow_redirects=False) as client:
            response = client.get(_object_url(storage_key), headers=_remote_headers())
            if response.status_code == status.HTTP_404_NOT_FOUND:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Private evidence object is not available")
            response.raise_for_status()
        temporary.write_bytes(response.content)
        os.replace(temporary, cached)
        return cached
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except httpx.HTTPError as exc:
        temporary.unlink(missing_ok=True)
        raise _remote_failure("download", exc) from exc


def delete_private_object(storage_key: str) -> None:
    storage_key = _safe_storage_key(storage_key)
    if not using_supabase_storage():
        candidate = (settings.storage_root / storage_key).resolve()
        root = settings.storage_root.resolve()
        if root in candidate.parents:
            candidate.unlink(missing_ok=True)
        return
    try:
        if not settings.supabase_url or not settings.supabase_storage_bucket:
            raise RuntimeError("Supabase private storage configuration is unavailable")
        endpoint = "/".join([settings.supabase_url.rstrip("/"), "storage/v1/object", quote(settings.supabase_storage_bucket, safe="")])
        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            response = client.request("DELETE", endpoint, headers=_remote_headers(), json={"prefixes": [storage_key]})
            response.raise_for_status()
        _cache_path(storage_key, settings.storage_root).unlink(missing_ok=True)
    except httpx.HTTPError as exc:
        raise _remote_failure("cleanup", exc) from exc


async def persist_upload(upload: UploadFile, *, case_id: str, evidence_id: str) -> StoredFile:
    extension = _safe_extension(upload.filename)
    temporary_path = settings.storage_root / ".incoming" / f"{uuid4()}.part"
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    digest, prefix, total_bytes = hashlib.sha256(), b"", 0
    try:
        with temporary_path.open("xb") as stream:
            while chunk := await upload.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_size_bytes:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Evidence exceeds the configured size limit")
                if len(prefix) < 4096:
                    prefix += chunk[: 4096 - len(prefix)]
                digest.update(chunk)
                stream.write(chunk)
        if not total_bytes:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty evidence files are not accepted")
        detected_mime = detect_mime(prefix, extension)
        stored_name = f"{evidence_id}{extension}"
        relative_key = str(PurePosixPath("cases") / re.sub(r"[^a-zA-Z0-9-]", "", case_id) / stored_name)
        if using_supabase_storage():
            publish_private_file(temporary_path, relative_key, content_type=detected_mime)
        else:
            destination = settings.storage_root / relative_key
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary_path, destination)
        return StoredFile(relative_key, stored_name, extension, detected_mime, total_bytes, digest.hexdigest())
    finally:
        temporary_path.unlink(missing_ok=True)


def get_private_path(storage_key: str) -> Path:
    return materialize_private_file(storage_key, cache_root=settings.storage_root)


def report_storage_key(local_relative_key: str) -> str:
    safe = _safe_storage_key(local_relative_key)
    return f"reports/{safe}" if using_supabase_storage() else safe


def get_report_artifact_path(storage_key: str) -> Path:
    return materialize_private_file(storage_key, cache_root=settings.generated_reports_root)
