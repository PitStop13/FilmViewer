import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require
from app.auth.permissions import Permission
from app.config import configured_domain

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stream",
    tags=["stream"],
    dependencies=[
        Depends(
            require(
                Permission.VIEW_LIBRARY,
                Permission.REQUEST,
                Permission.DOWNLOAD,
                mode="or",
            )
        )
    ],
)


def _sc_domain() -> str:
    domain = configured_domain()
    if not domain:
        raise HTTPException(status_code=409, detail="Nessun dominio StreamingCommunity configurato")
    return domain


def _resolve_anime_embed(host: str, episode_id: str) -> str | None:
    try:
        from app.core.animeunity import _get_scraper
        scraper = _get_scraper()
        r = scraper.get(f"https://{host}/embed-url/{episode_id}", timeout=8)
        if r.ok:
            text = r.text.strip()
            if text.startswith("http"):
                return text
    except Exception as e:
        logger.debug("Failed to resolve AnimeUnity embed URL for episode %s: %s", episode_id, e)
    return None


@router.get("/watch-info")
async def get_watch_info(
    content_type: str = Query(..., alias="content_type"),
    id: str = Query(...),
    slug: str = Query(""),
    episode_id: Optional[str] = Query(None),
    episode_number: Optional[str] = Query(None),
):
    """Provide direct watch URL and embed player URL for online streaming."""
    c_type = (content_type or "").lower().strip()

    if c_type in ("movie", "film"):
        domain = _sc_domain()
        watch_url = f"https://{domain}/it/watch/{id}"
        embed_url = f"https://{domain}/it/iframe/{id}"
        return {
            "content_type": "movie",
            "id": id,
            "watch_url": watch_url,
            "embed_url": embed_url,
            "source_name": "StreamingCommunity",
        }

    if c_type in ("tv", "series"):
        domain = _sc_domain()
        if episode_id:
            watch_url = f"https://{domain}/it/watch/{id}?e={episode_id}"
            embed_url = f"https://{domain}/it/iframe/{id}?episode_id={episode_id}"
        else:
            watch_url = f"https://{domain}/it/titles/{id}-{slug}" if slug else f"https://{domain}/it/watch/{id}"
            embed_url = f"https://{domain}/it/iframe/{id}"
        return {
            "content_type": "tv",
            "id": id,
            "episode_id": episode_id,
            "watch_url": watch_url,
            "embed_url": embed_url,
            "source_name": "StreamingCommunity",
        }

    if c_type == "anime":
        host = os.getenv("ANIMEUNITY_HOST", "www.animeunity.so")
        ep_num = str(episode_number or "1")
        clean_slug = slug or id
        watch_url = f"https://{host}/anime/{id}-{clean_slug}/{ep_num}"

        embed_url = None
        if episode_id:
            embed_url = await asyncio.to_thread(_resolve_anime_embed, host, episode_id)

        # Fallback embed to watch page if direct embed not available
        if not embed_url:
            embed_url = watch_url

        return {
            "content_type": "anime",
            "id": id,
            "episode_id": episode_id,
            "episode_number": ep_num,
            "watch_url": watch_url,
            "embed_url": embed_url,
            "source_name": "AnimeUnity",
        }

    raise HTTPException(status_code=400, detail=f"Tipo di contenuto non valido: {content_type}")
