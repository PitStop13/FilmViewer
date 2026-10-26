import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
import re
import threading
from collections import OrderedDict

import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.auth.deps import require
from app.auth.permissions import Permission
from app.config import configured_domain
from app.core.headers import get_headers

logger = logging.getLogger(__name__)

# Posters accompany search results and the request queue, so approvers need
# them too even when they cannot search.
router = APIRouter(
    dependencies=[
        Depends(
            require(
                Permission.REQUEST,
                Permission.DOWNLOAD,
                Permission.MANAGE_REQUESTS,
                mode="or",
            )
        )
    ]
)

# Poster filenames come from a third-party API and end up in a URL, so they are
# constrained to what a filename can actually be.
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")

_MAX_IMAGE_CACHE_ENTRIES = 2000
_image_cache: OrderedDict[tuple[str, str], tuple[bytes, str]] = OrderedDict()
_image_cache_lock = threading.Lock()

# Negative cache for missing images (404s) to avoid repeatedly hammering CDN
_negative_cache: dict[tuple[str, str], float] = {}
_negative_cache_lock = threading.Lock()
_NEGATIVE_TTL = 300.0  # 5 minutes

# Dedicated thread pool for image proxying to avoid starving the main asyncio thread pool
_IMAGE_EXECUTOR = ThreadPoolExecutor(max_workers=16, thread_name_prefix="img-proxy")

# Persistent disk cache directory
_IMAGE_CACHE_DIR = Path("tmp") / "img_cache"
try:
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception as _e:
    logger.warning("Could not create img_cache directory: %s", _e)

_image_session: requests.Session | None = None
_image_session_lock = threading.Lock()


def _get_image_session() -> requests.Session:
    global _image_session
    if _image_session is None:
        with _image_session_lock:
            if _image_session is None:
                s = requests.Session()
                adapter = requests.adapters.HTTPAdapter(pool_connections=24, pool_maxsize=24, max_retries=1)
                s.mount("https://", adapter)
                s.mount("http://", adapter)
                _image_session = s
    return _image_session


def _disk_cache_path(filename: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    return _IMAGE_CACHE_DIR / safe_name


def _guess_media_type(filename: str) -> str:
    fn = filename.lower()
    if fn.endswith(".webp"):
        return "image/webp"
    if fn.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if fn.endswith(".png"):
        return "image/png"
    if fn.endswith(".gif"):
        return "image/gif"
    if fn.endswith(".svg"):
        return "image/svg+xml"
    return "image/jpeg"


def get_cached_image(domain: str, filename: str) -> tuple[bytes, str] | None:
    # 1. Check memory cache
    with _image_cache_lock:
        if (domain, filename) in _image_cache:
            _image_cache.move_to_end((domain, filename))
            return _image_cache[(domain, filename)]

    # 2. Check disk cache
    try:
        disk_file = _disk_cache_path(filename)
        if disk_file.is_file() and disk_file.stat().st_size > 0:
            content = disk_file.read_bytes()
            media_type = _guess_media_type(filename)
            store_cached_image(domain, filename, content, media_type)
            return content, media_type
    except Exception:
        pass

    return None


def store_cached_image(domain: str, filename: str, content: bytes, content_type: str) -> None:
    with _image_cache_lock:
        _image_cache[(domain, filename)] = (content, content_type)
        if len(_image_cache) > _MAX_IMAGE_CACHE_ENTRIES:
            _image_cache.popitem(last=False)

    # Persist to disk in background/non-blocking fashion
    try:
        disk_file = _disk_cache_path(filename)
        if not disk_file.exists():
            disk_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = disk_file.with_suffix(".tmp")
            tmp_file.write_bytes(content)
            tmp_file.replace(disk_file)
    except Exception as e:
        logger.debug("Failed saving image to disk cache %s: %s", filename, e)


def clear_image_cache() -> None:
    with _image_cache_lock:
        _image_cache.clear()
    with _negative_cache_lock:
        _negative_cache.clear()
    try:
        if _IMAGE_CACHE_DIR.exists():
            for f in _IMAGE_CACHE_DIR.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass


def _fetch_image(domain: str, filename: str) -> tuple[bytes, str]:
    """Fetch image from CDN or main domain (blocking, runs in dedicated worker thread)."""
    cached = get_cached_image(domain, filename)
    if cached is not None:
        return cached

    now = asyncio.get_event_loop().time() if asyncio._get_running_loop() else 0
    with _negative_cache_lock:
        exp = _negative_cache.get((domain, filename))
        if exp and exp > now:
            raise HTTPException(status_code=404, detail="Image not found (cached miss)")

    candidates = [
        f"https://cdn.{domain}/images/{filename}",
        f"https://{domain}/images/{filename}",
    ]
    session = _get_image_session()
    last_status = 404
    for url in candidates:
        try:
            res = session.get(
                url,
                headers={
                    "user-agent": get_headers(),
                    "referer": f"https://{domain}/",
                },
                timeout=(2.0, 3.5),
                stream=True,
            )
            content_type = res.headers.get("content-type", "")
            if res.ok and (content_type.startswith("image/") or content_type == "application/octet-stream"):
                actual_type = content_type if content_type.startswith("image/") else _guess_media_type(filename)
                store_cached_image(domain, filename, res.content, actual_type)
                return res.content, actual_type
            last_status = res.status_code
        except Exception as e:
            logger.debug("Image proxy attempt failed for %s: %s", url, e)

    with _negative_cache_lock:
        _negative_cache[(domain, filename)] = (now or 0) + _NEGATIVE_TTL
        if len(_negative_cache) > 2000:
            _negative_cache.clear()

    raise HTTPException(status_code=last_status, detail="Image not found")


@router.get("/api/image/{filename:path}")
async def proxy_image(filename: str):
    """Proxy images from the streaming site to avoid hotlink protection.

    Uses dedicated ThreadPoolExecutor and disk caching to prevent thread starvation.
    """
    domain = configured_domain()
    if not domain:
        raise HTTPException(status_code=409, detail="Nessun dominio configurato")
    if ".." in filename or not SAFE_FILENAME.match(filename):
        raise HTTPException(status_code=400, detail="Nome file non valido")

    # Fast disk/memory cache check directly in async loop (instant response without entering thread pool)
    cached = get_cached_image(domain, filename)
    if cached is not None:
        content, content_type = cached
        return Response(
            content=content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=2592000, immutable"},
        )

    loop = asyncio.get_running_loop()
    content, content_type = await loop.run_in_executor(_IMAGE_EXECUTOR, _fetch_image, domain, filename)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=2592000, immutable"},
    )
