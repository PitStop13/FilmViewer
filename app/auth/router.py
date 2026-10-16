"""Authentication routes: status, session, logout, current user."""

import logging

from fastapi import APIRouter, Request, Response

from app import __version__
from app.auth import models, session as sessions
from app.auth.deps import current_user
from app.config import COOKIE_SAMESITE, COOKIE_SECURE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, raw_token: str):
    response.set_cookie(
        sessions.SESSION_COOKIE,
        raw_token,
        max_age=int(sessions.SESSION_TTL.total_seconds()),
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        path="/",
    )


def _session_payload(user: models.User, csrf_token: str | None) -> dict:
    return {
        "user": user.to_public(),
        "csrf_token": csrf_token,
        "auth_enabled": not models.runtime_open_mode(),
        "version": __version__,
    }


@router.get("/status")
def auth_status():
    """Public: tells the frontend that auth is not enabled / panel is in open mode."""
    return {"setup_done": True, "jellyfin_url": None, "auth_enabled": False}


@router.post("/skip")
def skip_setup():
    """No-op kept for backwards compatibility."""
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    sessions.delete_session(request.cookies.get(sessions.SESSION_COOKIE, ""))
    response.delete_cookie(sessions.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    return _session_payload(user, getattr(request.state, "csrf_token", None))
