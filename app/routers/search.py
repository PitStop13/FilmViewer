import asyncio
import logging
import threading
import time
from collections import OrderedDict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require
from app.auth.permissions import Permission
from app.config import configured_domain
from app.core.page import search as core_search, browse_archive
from app.core.film import get_film_languages
from app.core.tv import get_tv_languages

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(require(Permission.REQUEST, Permission.DOWNLOAD, mode="or"))],
)

Source = Literal["streamingcommunity"]

_SEARCH_CACHE: OrderedDict[tuple, tuple[float, list]] = OrderedDict()
_SEARCH_LOCK = threading.Lock()
_SEARCH_TTL = 5 * 60  # 5 minutes
_MAX_SEARCH_ENTRIES = 300


def get_cached_search(key: tuple) -> list | None:
    now = time.time()
    with _SEARCH_LOCK:
        if key in _SEARCH_CACHE:
            exp, val = _SEARCH_CACHE[key]
            if exp > now:
                _SEARCH_CACHE.move_to_end(key)
                return val
            _SEARCH_CACHE.pop(key, None)
    return None


def store_cached_search(key: tuple, val: list) -> None:
    now = time.time()
    with _SEARCH_LOCK:
        _SEARCH_CACHE[key] = (now + _SEARCH_TTL, val)
        if len(_SEARCH_CACHE) > _MAX_SEARCH_ENTRIES:
            _SEARCH_CACHE.popitem(last=False)


def clear_search_cache() -> None:
    with _SEARCH_LOCK:
        _SEARCH_CACHE.clear()


def _domain() -> str:
    domain = configured_domain()
    if not domain:
        raise HTTPException(status_code=409, detail="Nessun dominio configurato")
    return domain


@router.get("")
async def search(
    q: str = Query(default="", max_length=200),
    source: Source = Query(default="streamingcommunity"),
    page: int = Query(default=1, ge=1, le=50),
    media_type: str | None = Query(default=None),
    dubbed: bool = Query(default=False),
    sort: str = Query(default="views"),
):
    if dubbed:
        raise HTTPException(status_code=422, detail="dubbed non è supportato per streamingcommunity")
    if media_type is not None and media_type not in ("movie", "tv"):
        raise HTTPException(status_code=422, detail=f"media_type '{media_type}' non supportato per streamingcommunity")

    domain = _domain()
    clean_q = (q or "").strip()
    cache_key = (domain, clean_q, page, media_type, sort if not clean_q else "")
    cached = get_cached_search(cache_key)
    if cached is not None:
        return cached

    try:
        if not clean_q:
            results = await asyncio.to_thread(
                browse_archive, domain, page=page, media_type=media_type, sort=sort)
        else:
            results = await asyncio.to_thread(
                core_search, clean_q, domain, page=page, media_type=media_type)
        store_cached_search(cache_key, results)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Search error")
        raise HTTPException(status_code=502, detail=str(e))
    return results


@router.get("/languages/{title_id}")
async def title_languages(
    title_id: int,
    type: str = Query(..., pattern="^(movie|tv)$"),
    slug: str = Query(default=None),
    version: str = Query(default=""),
):
    domain = _domain()
    try:
        if type == "movie":
            langs = await asyncio.to_thread(get_film_languages, title_id, domain)
        else:
            if not slug:
                raise ValueError("slug is required for tv type")
            langs = await asyncio.to_thread(get_tv_languages, title_id, slug, domain, version)
    except Exception as e:
        logger.warning("Languages fetch error for %s %d: %s", type, title_id, e)
        raise HTTPException(status_code=502, detail=str(e))
    return langs
