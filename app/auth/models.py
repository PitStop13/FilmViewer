"""Data access for panel settings and users."""

import base64
import hashlib
import json
import logging
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from app import db
from app.auth import permissions as perms

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def device_id_for(username: str) -> str:
    return base64.b64encode(f"SCPanel_{username}".encode()).decode()


# ── Password Hashing ───────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a unique salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"pbkdf2:sha256:100000${salt}${dk.hex()}"


def verify_password(password: str, hashed: str | None) -> bool:
    """Verify a password against a PBKDF2-HMAC-SHA256 hash."""
    if not hashed or not password:
        return False
    try:
        method, salt, key = hashed.split("$")
        algo, iter_str = method.split(":")[1:]
        iterations = int(iter_str)
        dk = hashlib.pbkdf2_hmac(algo, password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return secrets.compare_digest(dk.hex(), key)
    except Exception:
        return False


# ── Parental Control ───────────────────────────────────────────────────────────

def parse_age(raw_age) -> int | None:
    if raw_age is None:
        return None
    s = str(raw_age).strip()
    if not s:
        return None
    s = s.replace("+", "").upper().replace("VM", "").strip()
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def is_title_allowed_for_profile(raw_age, profile: str = "adult") -> bool:
    """All users have access to all titles (no parental restrictions)."""
    return True



# ── Settings ───────────────────────────────────────────────────────────────────

SETTING_DEFAULT_PERMISSIONS = "default_permissions"
SETTING_AUTH_MODE = "auth_mode"

_SETTING_DEFAULTS = {
    SETTING_AUTH_MODE: "local",
    SETTING_DEFAULT_PERMISSIONS: str(int(perms.DEFAULT_PERMISSIONS)),
}


def get_setting(key: str, default: str | None = None) -> str | None:
    row = db.query_one("SELECT value FROM jf_setting WHERE key = ?", (key,))
    if row is not None:
        return row["value"]
    return _SETTING_DEFAULTS.get(key, default)


def set_setting(key: str, value: str, conn: sqlite3.Connection | None = None):
    (conn or db.get_conn()).execute(
        "INSERT INTO jf_setting(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def default_permissions() -> int:
    try:
        return perms.sanitize(int(get_setting(SETTING_DEFAULT_PERMISSIONS)))
    except (TypeError, ValueError):
        return int(perms.DEFAULT_PERMISSIONS)


def setup_done() -> bool:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM jf_user WHERE enabled = 1 AND password_hash IS NOT NULL AND password_hash != ''"
    )
    return (int(row["n"]) if row else 0) > 0


def runtime_open_mode() -> bool:
    return get_setting(SETTING_AUTH_MODE, "local") == "open"




VALID_THEMES = {
    "default",
    "rose",
    "emerald",
    "amber",
    "light",
    "purple",
    "cyan",
    "oled",
    "crimson",
}


# ── Users ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class User:
    id: int
    jellyfin_user_id: str
    username: str
    is_jellyfin_admin: bool
    permissions: int
    enabled: bool
    device_id: str
    created_at: str
    last_login_at: str | None
    parental_control: str = "adult"
    password_hash: str | None = None
    theme: str = "default"

    @property
    def is_admin(self) -> bool:
        return bool(self.is_jellyfin_admin or (self.permissions & perms.Permission.MANAGE_SETTINGS != 0))

    @property
    def permission_names(self) -> list[str]:
        return perms.to_names(self.permissions)

    def has(self, *required, mode: str = "and") -> bool:
        return perms.has(self.permissions, *required, mode=mode)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "is_admin": self.is_admin,
            "is_jellyfin_admin": self.is_jellyfin_admin,
            "permissions": self.permissions,
            "permission_names": self.permission_names,
            "parental_control": self.parental_control,
            "theme": self.theme,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
        }


def _row_to_user(row: sqlite3.Row) -> User:
    parental_control = "adult"
    password_hash = None
    theme = "default"
    try:
        parental_control = row["parental_control"] or "adult"
    except (IndexError, KeyError):
        pass
    try:
        password_hash = row["password_hash"]
    except (IndexError, KeyError):
        pass
    try:
        theme = row["theme"] or "default"
    except (IndexError, KeyError):
        pass

    return User(
        id=row["id"],
        jellyfin_user_id=row["jellyfin_user_id"] or "",
        username=row["username"],
        is_jellyfin_admin=bool(row["is_jellyfin_admin"]),
        permissions=row["permissions"],
        enabled=bool(row["enabled"]),
        device_id=row["device_id"] or "",
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
        parental_control=parental_control,
        password_hash=password_hash,
        theme=theme,
    )


def get_user(user_id: int) -> User | None:
    row = db.query_one("SELECT * FROM jf_user WHERE id = ?", (user_id,))
    return _row_to_user(row) if row else None


def get_user_by_username(username: str) -> User | None:
    if not username:
        return None
    row = db.query_one("SELECT * FROM jf_user WHERE LOWER(username) = LOWER(?)", (username.strip(),))
    return _row_to_user(row) if row else None


def get_user_by_jellyfin_id(jellyfin_user_id: str) -> User | None:
    row = db.query_one(
        "SELECT * FROM jf_user WHERE jellyfin_user_id = ?", (jellyfin_user_id,)
    )
    return _row_to_user(row) if row else None


def list_users() -> list[User]:
    rows = db.query("SELECT * FROM jf_user ORDER BY username COLLATE NOCASE")
    return [_row_to_user(r) for r in rows]


def count_users() -> int:
    row = db.query_one("SELECT COUNT(*) AS n FROM jf_user WHERE password_hash IS NOT NULL AND password_hash != ''")
    return int(row["n"]) if row else 0


def count_admins() -> int:
    return db.query_one(
        "SELECT COUNT(*) AS n FROM jf_user WHERE enabled = 1 AND (is_jellyfin_admin = 1 OR (permissions & ?) != 0)",
        (int(perms.Permission.MANAGE_SETTINGS),),
    )["n"]


def create_local_user(
    username: str,
    password: str,
    is_admin: bool = False,
    parental_control: str = "adult",
    permissions: int | None = None,
) -> User:
    clean_username = (username or "").strip()
    if not clean_username:
        raise ValueError("Il nome utente non può essere vuoto")
    if not re.match(r"^[\w\.\-]+$", clean_username, re.UNICODE):
        raise ValueError("Il nome utente contiene caratteri non validi")

    existing = get_user_by_username(clean_username)
    if existing is not None:
        if existing.password_hash:
            raise ValueError(f"L'utente '{clean_username}' esiste già")
        # Remove legacy record without password so it can be created fresh
        db.execute("DELETE FROM jf_user WHERE id = ?", (existing.id,))


    prof = (parental_control or "adult").strip().lower()
    if prof not in ("adult", "teen", "kid"):
        prof = "adult"

    if permissions is None:
        effective_perms = int(perms.ALL_PERMISSIONS) if is_admin else int(perms.DEFAULT_PERMISSIONS)
    else:
        effective_perms = perms.sanitize(permissions)

    pwd_hash = hash_password(password) if password else None
    local_id = f"local_{secrets.token_hex(8)}"
    now = now_iso()

    with db.tx() as conn:
        if existing is not None:
            conn.execute("DELETE FROM jf_user WHERE id = ?", (existing.id,))
        cursor = conn.execute(
            """
            INSERT INTO jf_user(
                jellyfin_user_id, username, is_jellyfin_admin, permissions,
                enabled, device_id, created_at, password_hash, parental_control
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                local_id,
                clean_username,
                int(is_admin),
                effective_perms,
                1,
                device_id_for(clean_username),
                now,
                pwd_hash,
                prof,
            ),
        )
        user_id = cursor.lastrowid
        # When first user is created, set auth mode to local
        set_setting(SETTING_AUTH_MODE, "local", conn=conn)

    return get_user(user_id)


def update_local_user(
    user_id: int,
    username: str | None = None,
    password: str | None = None,
    parental_control: str | None = None,
    is_admin: bool | None = None,
    enabled: bool | None = None,
    theme: str | None = None,
) -> User:
    user = get_user(user_id)
    if not user:
        raise ValueError("Utente non trovato")

    updates = []
    params = []

    if username is not None:
        clean_user = username.strip()
        if not clean_user:
            raise ValueError("Il nome utente non può essere vuoto")
        existing = get_user_by_username(clean_user)
        if existing and existing.id != user_id:
            raise ValueError(f"Il nome utente '{clean_user}' è già in uso")
        updates.append("username = ?")
        params.append(clean_user)
        updates.append("device_id = ?")
        params.append(device_id_for(clean_user))

    if password is not None and password.strip():
        updates.append("password_hash = ?")
        params.append(hash_password(password.strip()))

    if parental_control is not None:
        prof = parental_control.strip().lower()
        if prof in ("adult", "teen", "kid"):
            updates.append("parental_control = ?")
            params.append(prof)

    if theme is not None:
        clean_theme = theme.strip().lower()
        if clean_theme in VALID_THEMES:
            updates.append("theme = ?")
            params.append(clean_theme)

    if is_admin is not None:
        if not is_admin and user.is_admin and count_admins() <= 1:
            raise ValueError("Non è possibile rimuovere i permessi di amministratore all'ultimo amministratore attivo")
        updates.append("is_jellyfin_admin = ?")
        params.append(int(is_admin))
        if is_admin:
            updates.append("permissions = ?")
            params.append(int(perms.ALL_PERMISSIONS))
        else:
            updates.append("permissions = ?")
            params.append(int(perms.DEFAULT_PERMISSIONS))


    if enabled is not None:
        if not enabled and user.is_admin and count_admins() <= 1:
            raise ValueError("Non è possibile disabilitare l'ultimo amministratore attivo")
        updates.append("enabled = ?")
        params.append(int(enabled))

    if updates:
        params.append(user_id)
        with db.tx() as conn:
            conn.execute(f"UPDATE jf_user SET {', '.join(updates)} WHERE id = ?", params)
            if enabled is False:
                conn.execute("DELETE FROM jf_session WHERE user_id = ?", (user_id,))

    return get_user(user_id)


def update_user_theme(user_id: int, theme: str) -> str:
    """Update UI color theme preference for a specific user."""
    clean_theme = (theme or "default").strip().lower()
    if clean_theme not in VALID_THEMES:
        clean_theme = "default"
    with db.tx() as conn:
        conn.execute("UPDATE jf_user SET theme = ? WHERE id = ?", (clean_theme, user_id))
    return clean_theme


def delete_local_user(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        raise ValueError("Utente non trovato")
    if user.is_admin and count_admins() <= 1:
        raise ValueError("Non è possibile eliminare l'ultimo amministratore")

    with db.tx() as conn:
        admin = conn.execute(
            "SELECT id FROM jf_user WHERE is_jellyfin_admin = 1 AND id != ? ORDER BY id ASC LIMIT 1",
            (user_id,),
        ).fetchone()
        admin_id = admin["id"] if admin else None

        tables = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        if "jf_request" in tables:
            if admin_id:
                conn.execute("UPDATE jf_request SET requested_by = ? WHERE requested_by = ?", (admin_id, user_id))
                conn.execute("UPDATE jf_request SET decided_by = ? WHERE decided_by = ?", (admin_id, user_id))
            else:
                conn.execute("UPDATE jf_request SET decided_by = NULL WHERE decided_by = ?", (user_id,))

        if "jf_series_watch" in tables:
            if admin_id:
                conn.execute("UPDATE jf_series_watch SET created_by = ? WHERE created_by = ?", (admin_id, user_id))
            else:
                conn.execute("UPDATE jf_series_watch SET created_by = NULL WHERE created_by = ?", (user_id,))

        if "jf_webhook" in tables:
            if admin_id:
                conn.execute("UPDATE jf_webhook SET created_by = ? WHERE created_by = ?", (admin_id, user_id))
            else:
                conn.execute("UPDATE jf_webhook SET created_by = NULL WHERE created_by = ?", (user_id,))

        for tbl in (
            "jf_session",
            "continue_watching",
            "jf_request_subscriber",
            "jf_series_watch_subscriber",
            "jf_notification",
        ):
            if tbl in tables:
                cols = {c[1] for c in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
                if "user_id" in cols:
                    conn.execute(f"DELETE FROM {tbl} WHERE user_id = ?", (user_id,))

        conn.execute("DELETE FROM jf_user WHERE id = ?", (user_id,))
    logger.info("Deleted local user %s (id=%d)", user.username, user_id)
    return True


def create_user(
    jellyfin_user_id: str,
    username: str,
    permissions: int,
    is_jellyfin_admin: bool = False,
    enabled: bool = True,
    conn: sqlite3.Connection | None = None,
) -> User:
    executor = conn or db.get_conn()
    executor.execute(
        "INSERT INTO jf_user(jellyfin_user_id, username, is_jellyfin_admin, permissions, "
        "enabled, device_id, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
        (
            jellyfin_user_id,
            username,
            int(is_jellyfin_admin),
            perms.sanitize(permissions),
            int(enabled),
            device_id_for(username),
            now_iso(),
        ),
    )
    row = executor.execute(
        "SELECT * FROM jf_user WHERE jellyfin_user_id = ?", (jellyfin_user_id,)
    ).fetchone()
    return _row_to_user(row)


def touch_login(user_id: int, username: str, is_jellyfin_admin: bool):
    """Refresh the cached display name and admin flag after a successful login.

    The username is only a cache — Jellyfin allows renaming, so the stored value
    would otherwise drift away from reality. The device id follows the username,
    so a rename produces one new Jellyfin device and then stays stable again.
    """
    db.execute(
        "UPDATE jf_user SET username = ?, is_jellyfin_admin = ?, device_id = ?, "
        "last_login_at = ? WHERE id = ?",
        (username, int(is_jellyfin_admin), device_id_for(username), now_iso(), user_id),
    )


def set_permissions(user_id: int, permissions: int):
    db.execute(
        "UPDATE jf_user SET permissions = ? WHERE id = ?",
        (perms.sanitize(permissions), user_id),
    )


def set_enabled(user_id: int, enabled: bool):
    """Enable or disable a user.

    Disabling drops the user's sessions in the same transaction, which is what
    makes revocation immediate rather than "immediate once the token expires".
    """
    with db.tx() as conn:
        conn.execute("UPDATE jf_user SET enabled = ? WHERE id = ?", (int(enabled), user_id))
        if not enabled:
            conn.execute("DELETE FROM jf_session WHERE user_id = ?", (user_id,))


def count_users_with(permission) -> int:
    """How many enabled users hold a permission bit (used to prevent lockout)."""
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM jf_user WHERE enabled = 1 AND (permissions & ?) != 0",
        (int(permission),),
    )
    return row["n"]


def json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
