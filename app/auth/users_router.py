"""User management endpoints for administrators."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import models
from app.auth.deps import current_user, require
from app.auth.permissions import Permission

logger = logging.getLogger(__name__)


def require_local_admin(request: Request):
    if models.runtime_open_mode():
        raise HTTPException(status_code=403, detail="Gestione utenti non disponibile in modalità aperta")
    user = current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Permesso negato")
    return user


router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[
        Depends(require_local_admin),
        Depends(require(Permission.MANAGE_SETTINGS)),
    ],
)


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False
    parental_control: str = "adult"


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    parental_control: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("")
def list_all_users():
    """List all registered users."""
    users = models.list_users()
    return [u.to_public() for u in users]


@router.get("/profiles")
def list_profiles():
    """List available parental control profiles."""
    return [
        {
            "id": "adult",
            "name": "Adulti",
            "description": "Tutti i contenuti sono visibili e riproducibili.",
        },
        {
            "id": "teen",
            "name": "Ragazzi",
            "description": "Consente tutti i film e serie fino a 16 anni inclusi. Blocca i contenuti +18.",
        },
        {
            "id": "kid",
            "name": "Bambini",
            "description": "Consente solo contenuti per tutti. Vieta categoricamente film e serie +13 e superiori.",
        },
    ]


@router.post("")
def create_user(body: CreateUserRequest):
    """Create a new local user."""
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
            is_admin=body.is_admin,
            parental_control=body.parental_control,
        )
        return user.to_public()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}")
def update_user(user_id: int, body: UpdateUserRequest):
    """Update user attributes."""
    try:
        user = models.update_local_user(
            user_id=user_id,
            username=body.username,
            password=body.password,
            parental_control=body.parental_control,
            is_admin=body.is_admin,
            enabled=body.enabled,
        )
        return user.to_public()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_id}")
def delete_user(user_id: int):
    """Delete a user account."""
    try:
        models.delete_local_user(user_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Errore eliminazione utente %d: %s", user_id, e)
        raise HTTPException(status_code=400, detail=f"Errore durante l'eliminazione dell'utente: {e}")
