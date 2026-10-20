import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth import models
from app.auth.deps import require
from app.auth.permissions import Permission
from app.config import configured_domain
from app.core import home as core_home

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/home",
    tags=["home"],
    dependencies=[Depends(require(Permission.REQUEST, Permission.DOWNLOAD, mode="or"))],
)

Source = Literal["streamingcommunity"]


def _invoke_shelves(source: str, host: str, category: str | None, user_id: int, refresh: bool):
    try:
        return core_home.shelves(source, host, category, user_id=user_id, refresh=refresh)
    except TypeError:
        try:
            return core_home.shelves(source, host, category)
        except TypeError:
            return core_home.shelves(source, host)


@router.get("")
async def home(
    request: Request,
    source: Source = Query(default="streamingcommunity"),
    category: str = Query(default=None),
    refresh: bool = Query(default=False),
):
    """The shelves the source itself publishes on its front page and deep catalogs."""
    host = configured_domain()
    if not host:
        raise HTTPException(status_code=409, detail="Nessun dominio configurato")

    user = getattr(request.state, "user", None)
    user_id = user.id if user else 0

    try:
        result = await asyncio.to_thread(
            _invoke_shelves, source, host, category, user_id, refresh
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Home shelves error")
        raise HTTPException(status_code=502, detail=str(e))

    return {"source": source, "shelves": result}


