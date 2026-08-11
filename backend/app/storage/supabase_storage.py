from __future__ import annotations

import hashlib
import os
from typing import Optional

import requests


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upload_private(*, user_id: str, filename: str, data: bytes, content_type: str = "application/octet-stream") -> Optional[str]:
    """Upload a private attachment to Supabase Storage when persistence is enabled."""
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "email-attachments")
    if not base or not key:
        return None
    safe_name = filename.replace("/", "_").replace("\\", "_")
    path = f"{user_id}/{content_hash(data)}/{safe_name}"
    response = requests.post(
        f"{base}/storage/v1/object/{bucket}/{path}",
        headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": content_type, "x-upsert": "true"},
        data=data,
        timeout=60,
    )
    response.raise_for_status()
    return path
