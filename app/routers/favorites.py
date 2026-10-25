import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app import favorites as fav_service
from app.auth.deps import require
from app.auth.permissions import Permission

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/favorites",
    tags=["favorites"],
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


class FavoritePayload(BaseModel):
    media_type: str  # movie | tv
    content_id: str
    title: str
    slug: Optional[str] = ""
    poster: Optional[str] = None
    year: Optional[str] = None
    score: Optional[str] = None
    plot: Optional[str] = None


@router.get("")
async def get_favorites(
    request: Request,
    type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    user = getattr(request.state, "user", None)
    user_id = user.id if user else 0
    items = fav_service.get_favorites_list(user_id=user_id, media_type=type, limit=limit)
    return {"items": items}


@router.get("/status")
async def get_favorite_status(
    request: Request,
    media_type: str = Query(...),
    content_id: str = Query(...),
):
    user = getattr(request.state, "user", None)
    user_id = user.id if user else 0
    favorited = fav_service.is_favorite(media_type, content_id, user_id=user_id)
    return {"favorited": favorited}


@router.post("")
async def add_favorite(payload: FavoritePayload, request: Request):
    user = getattr(request.state, "user", None)
    user_id = user.id if user else 0
    try:
        res = fav_service.add_favorite(
            media_type=payload.media_type,
            content_id=payload.content_id,
            title=payload.title,
            slug=payload.slug or "",
            poster=payload.poster,
            year=payload.year,
            score=payload.score,
            plot=payload.plot,
            user_id=user_id,
        )
        return res
    except Exception as e:
        logger.exception("Error adding favorite")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{media_type}/{content_id}")
async def delete_favorite(media_type: str, content_id: str, request: Request):
    user = getattr(request.state, "user", None)
    user_id = user.id if user else 0
    try:
        fav_service.remove_favorite(media_type, content_id, user_id=user_id)
        return {"status": "ok", "favorited": False}
    except Exception as e:
        logger.exception("Error deleting favorite")
        raise HTTPException(status_code=500, detail=str(e))
