"""数据管道共用工具。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

USER_AGENT = (
    "cnjp-holiday-data/1.0 "
    "(+https://github.com/; holiday data pipeline)"
)
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


class ValidationError(RuntimeError):
    """生成的数据未通过校验时抛出。"""


def http_get(url: str, *, timeout: int = REQUEST_TIMEOUT, retries: int = REQUEST_RETRIES) -> bytes:
    """带重试和退避的 GET 请求。"""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = SESSION.get(url, timeout=timeout)
            response.raise_for_status()
            return response.content
        except requests.RequestException as error:  # pragma: no cover - network
            last_error = error
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_error}")


def http_get_text(
    url: str,
    *,
    encoding: str = "utf-8",
    timeout: int = REQUEST_TIMEOUT,
    retries: int = REQUEST_RETRIES,
) -> str:
    return http_get(url, timeout=timeout, retries=retries).decode(encoding)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def json_dumps(document: Any) -> str:
    """稳定的 JSON 序列化：键排序、UTF-8、末尾换行。"""
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, document: Any) -> bool:
    """原子写入 JSON。返回文件内容是否发生变化。"""
    content = json_dumps(document).encode("utf-8")
    if path.exists() and path.read_bytes() == content:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return True
