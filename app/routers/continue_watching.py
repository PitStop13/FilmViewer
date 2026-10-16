import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app import continue_watching as cw_service
from app.auth.deps import require
from app.auth.permissions import Permission

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/continue-watching",
    tags=["continue-watching"],
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


class ProgressPayload(BaseModel):
    content_type: str
    content_id: str
    title: str
    position_seconds: float
    duration_seconds: float
    slug: Optional[str] = ""
    poster: Optional[str] = None
    episode_id: Optional[str] = None
    episode_number: Optional[int] = None
    season_number: Optional[int] = None
    episode_title: Optional[str] = None


class DeletePayload(BaseModel):
    content_type: str
    content_id: str


@router.get("")
async def get_continue_watching(limit: int = Query(default=30, ge=1, le=100)):
    items = cw_service.get_continue_watching_list(limit=limit)
    return {"items": items}


@router.post("/progress")
async def save_playback_progress(payload: ProgressPayload):
    try:
        res = cw_service.save_progress(
            content_type=payload.content_type,
            content_id=payload.content_id,
            title=payload.title,
            position_seconds=payload.position_seconds,
            duration_seconds=payload.duration_seconds,
            slug=payload.slug or "",
            poster=payload.poster,
            episode_id=payload.episode_id,
            episode_number=payload.episode_number,
            season_number=payload.season_number,
            episode_title=payload.episode_title,
        )
        return res
    except Exception as e:
        logger.exception("Error saving playback progress")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete")
async def delete_continue_watching(payload: DeletePayload):
    try:
        cw_service.delete_item(payload.content_type, payload.content_id)
        return {"status": "ok", "deleted": True}
    except Exception as e:
        logger.exception("Error deleting continue watching record")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{content_type}/{content_id}")
async def delete_continue_watching_param(content_type: str, content_id: str):
    try:
        cw_service.delete_item(content_type, content_id)
        return {"status": "ok", "deleted": True}
    except Exception as e:
        logger.exception("Error deleting continue watching record")
        raise HTTPException(status_code=500, detail=str(e))
