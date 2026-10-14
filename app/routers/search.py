import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require
from app.auth.permissions import Permission
from app.config import configured_domain
from app.core import animeunity
from app.core.page import search as core_search, browse_archive
from app.core.film import get_film_languages
from app.core.tv import get_tv_languages

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(require(Permission.REQUEST, Permission.DOWNLOAD, mode="or"))],
)

Source = Literal["streamingcommunity", "animeunity"]


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
    if source == "streamingcommunity":
        if dubbed:
            raise HTTPException(status_code=422, detail="dubbed non è supportato per streamingcommunity")
        if media_type is not None and media_type not in ("movie", "tv"):
            raise HTTPException(status_code=422, detail=f"media_type '{media_type}' non supportato per streamingcommunity")

        domain = _domain()
        try:
            if not q or not q.strip():
                results = await asyncio.to_thread(
                    browse_archive, domain, page=page, media_type=media_type, sort=sort)
            else:
                results = await asyncio.to_thread(
                    core_search, q, domain, page=page, media_type=media_type)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Search error")
            raise HTTPException(status_code=502, detail=str(e))
        return results

    if source == "animeunity":
        try:
            results = await asyncio.to_thread(
                animeunity.search, q, page=page, media_type=media_type, dubbed=dubbed
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("AnimeUnity search error")
            raise HTTPException(status_code=502, detail=str(e))
        return results

    raise HTTPException(status_code=422, detail="Source non supportata")


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
