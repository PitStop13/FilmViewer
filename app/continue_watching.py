"""Playback progress tracking and 'Continua a guardare' persistence."""

import logging
from datetime import datetime, timezone
from typing import Optional

from app import db

logger = logging.getLogger(__name__)


def make_id(content_type: str, content_id: str) -> str:
    c_type = (content_type or "").strip().lower()
    if c_type in ("movie", "film"):
        c_type = "movie"
    elif c_type in ("tv", "series"):
        c_type = "tv"
    return f"{c_type}:{str(content_id).strip()}"


def make_db_id(content_type: str, content_id: str, user_id: int = 0) -> str:
    return f"u{user_id}:{make_id(content_type, content_id)}"


def _row_to_dict(row) -> dict:
    duration = float(row["duration_seconds"] or 0)
    position = float(row["position_seconds"] or 0)
    percentage = int(min(100, max(0, round((position / duration) * 100)))) if duration > 0 else 0
    remaining_sec = max(0, int(duration - position)) if duration > 0 else 0

    user_id = 0
    try:
        user_id = int(row["user_id"] or 0)
    except (IndexError, KeyError, ValueError):
        pass

    c_type = (row["content_type"] or "").strip().lower()
    if c_type in ("movie", "film"):
        c_type = "movie"
    elif c_type in ("tv", "series"):
        c_type = "tv"

    return {
        "id": f"{c_type}:{str(row['content_id']).strip()}",
        "user_id": user_id,
        "content_type": row["content_type"],
        "content_id": row["content_id"],
        "slug": row["slug"] or "",
        "title": row["title"],
        "poster": row["poster"],
        "episode_id": row["episode_id"],
        "episode_number": row["episode_number"],
        "season_number": row["season_number"],
        "episode_title": row["episode_title"],
        "position_seconds": position,
        "duration_seconds": duration,
        "percentage": percentage,
        "remaining_seconds": remaining_sec,
        "updated_at": row["updated_at"],
    }


def get_continue_watching_list(user_id: int = 0, limit: int = 50) -> list[dict]:
    rows = db.query(
        "SELECT * FROM continue_watching WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
        (user_id, limit),
    )
    return [_row_to_dict(r) for r in rows]


def get_item(content_type: str, content_id: str, user_id: int = 0) -> Optional[dict]:
    db_id = make_db_id(content_type, content_id, user_id)
    legacy_id = make_id(content_type, content_id)
    row = db.query_one(
        "SELECT * FROM continue_watching WHERE id = ? OR (id = ? AND user_id = ?)",
        (db_id, legacy_id, user_id),
    )
    return _row_to_dict(row) if row else None


def delete_item(content_type: str, content_id: str, user_id: int = 0) -> bool:
    db_id = make_db_id(content_type, content_id, user_id)
    legacy_id = make_id(content_type, content_id)
    with db.tx() as conn:
        conn.execute(
            "DELETE FROM continue_watching WHERE id = ? OR (id = ? AND user_id = ?)",
            (db_id, legacy_id, user_id),
        )
    logger.info("Deleted continue watching record for %s (user_id=%d)", db_id, user_id)
    return True


def save_progress(
    content_type: str,
    content_id: str,
    title: str,
    position_seconds: float,
    duration_seconds: float,
    slug: str = "",
    poster: Optional[str] = None,
    episode_id: Optional[str] = None,
    episode_number: Optional[int] = None,
    season_number: Optional[int] = None,
    episode_title: Optional[str] = None,
    user_id: int = 0,
) -> dict:
    c_type = (content_type or "").strip().lower()
    if c_type in ("movie", "film"):
        c_type = "movie"
    elif c_type in ("tv", "series"):
        c_type = "tv"

    db_id = make_db_id(c_type, content_id, user_id)
    public_id = make_id(c_type, content_id)
    pos = max(0.0, float(position_seconds or 0))
    dur = max(0.0, float(duration_seconds or 0))

    # Finished condition: if >= 95% watched or fewer than 20 seconds remaining (with at least 1 min duration)
    if dur > 60 and (pos / dur >= 0.95 or (dur - pos) <= 20):
        delete_item(c_type, content_id, user_id)
        return {"status": "finished", "deleted": True}

    now = datetime.now(timezone.utc).isoformat()

    # If poster is not supplied, keep previous poster if existing
    if not poster:
        existing = db.query_one("SELECT poster FROM continue_watching WHERE id = ?", (db_id,))
        if existing and existing["poster"]:
            poster = existing["poster"]

    with db.tx() as conn:
        conn.execute(
            """
            INSERT INTO continue_watching (
                id, user_id, content_type, content_id, slug, title, poster,
                episode_id, episode_number, season_number, episode_title,
                position_seconds, duration_seconds, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id = excluded.user_id,
                content_type = excluded.content_type,
                content_id = excluded.content_id,
                slug = CASE WHEN excluded.slug != '' THEN excluded.slug ELSE continue_watching.slug END,
                title = excluded.title,
                poster = COALESCE(excluded.poster, continue_watching.poster),
                episode_id = excluded.episode_id,
                episode_number = excluded.episode_number,
                season_number = excluded.season_number,
                episode_title = excluded.episode_title,
                position_seconds = excluded.position_seconds,
                duration_seconds = excluded.duration_seconds,
                updated_at = excluded.updated_at
            """,
            (
                db_id,
                user_id,
                c_type,
                str(content_id),
                slug or "",
                title,
                poster,
                str(episode_id) if episode_id is not None else None,
                int(episode_number) if episode_number is not None else None,
                int(season_number) if season_number is not None else None,
                episode_title,
                pos,
                dur,
                now,
            ),
        )
    return {"status": "saved", "id": public_id}

