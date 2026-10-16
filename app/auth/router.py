"""Authentication routes: status, session, login, setup, logout, current user."""

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import __version__
from app.auth import models, session as sessions
from app.auth.deps import current_user
from app.config import COOKIE_SAMESITE, COOKIE_SECURE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


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
    """Public: tells whether setup has been completed and auth mode."""
    if models.runtime_open_mode():
        return {"setup_done": True, "jellyfin_url": None, "auth_enabled": False}
    if not models.setup_done():
        return {
            "setup_done": False,
            "jellyfin_url": None,
            "auth_enabled": True,
            "users_count": 0,
        }
    return {
        "setup_done": True,
        "jellyfin_url": None,
        "auth_enabled": True,
        "users_count": models.count_users(),
    }



@router.post("/setup")
def setup_admin(body: SetupRequest, response: Response):
    """First-run setup: creates the primary administrator account."""
    if models.setup_done():
        raise HTTPException(status_code=400, detail="Setup già completato. Effettua il login.")


    username = (body.username or "").strip()
    password = (body.password or "").strip()

    if not username:
        raise HTTPException(status_code=422, detail="Nome utente obbligatorio")
    if len(password) < 4:
        raise HTTPException(status_code=422, detail="La password deve contenere almeno 4 caratteri")

    try:
        user = models.create_local_user(
            username=username,
            password=password,
            is_admin=True,
            parental_control="adult",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    raw_token, csrf_token = sessions.create_session(user.id)
    _set_session_cookie(response, raw_token)
    logger.info("Admin user '%s' created successfully during setup", username)
    return _session_payload(user, csrf_token)


@router.post("/login")
def login(body: LoginRequest, response: Response):
    """Local user login with username and password."""
    username = (body.username or "").strip()
    password = (body.password or "").strip()

    if not username or not password:
        raise HTTPException(status_code=422, detail="Inserisci nome utente e password")

    user = models.get_user_by_username(username)
    if not user or not user.enabled or not models.verify_password(password, user.password_hash):
        logger.warning("Failed login attempt for username '%s'", username)
        raise HTTPException(status_code=401, detail="Nome utente o password non corretti")

    raw_token, csrf_token = sessions.create_session(user.id)
    _set_session_cookie(response, raw_token)
    models.touch_login(user.id, user.username, user.is_jellyfin_admin)
    logger.info("User '%s' logged in successfully", username)
    return _session_payload(user, csrf_token)


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

