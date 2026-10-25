"""User Favorites / Mi piace persistence."""

import logging
from datetime import datetime, timezone
from typing import Optional

from app import db

logger = logging.getLogger(__name__)


def make_fav_id(content_type: str, content_id: str, user_id: int = 0) -> str:
    c_type = "movie" if (content_type or "").strip().lower() in ("movie", "film") else "tv"
    return f"u{user_id}:{c_type}:{str(content_id).strip()}"


def _fav_row_to_dict(row) -> dict:
    c_type = "movie" if (row["media_type"] or "").strip().lower() in ("movie", "film") else "tv"
    user_id = 0
    try:
        user_id = int(row["user_id"] or 0)
    except (IndexError, KeyError, ValueError):
        pass

    return {
        "id": row["id"],
        "user_id": user_id,
        "media_type": c_type,
        "content_type": c_type,
        "content_id": str(row["content_id"]),
        "slug": row["slug"] or "",
        "title": row["title"],
        "poster": row["poster"],
        "year": row["year"],
        "score": row["score"],
        "plot": row["plot"],
        "created_at": row["created_at"],
    }


def get_favorites_list(user_id: int = 0, media_type: Optional[str] = None, limit: int = 100) -> list[dict]:
    """Retrieve favorites for the user, with fallback to user 0 in open mode."""
    c_type = None
    if media_type and media_type not in ("all", "*"):
        c_type = "movie" if media_type.lower() in ("movie", "film") else "tv"

    if user_id > 0:
        if c_type:
            rows = db.query(
                """
                SELECT * FROM favorites 
                WHERE (user_id = ? OR user_id = 0) AND media_type = ?
                ORDER BY (user_id = ?) DESC, created_at DESC 
                LIMIT ?
                """,
                (user_id, c_type, user_id, limit * 2),
            )
        else:
            rows = db.query(
                """
                SELECT * FROM favorites 
                WHERE user_id = ? OR user_id = 0 
                ORDER BY (user_id = ?) DESC, created_at DESC 
                LIMIT ?
                """,
                (user_id, user_id, limit * 2),
            )
    else:
        if c_type:
            rows = db.query(
                "SELECT * FROM favorites WHERE media_type = ? ORDER BY created_at DESC LIMIT ?",
                (c_type, limit * 2),
            )
        else:
            rows = db.query(
                "SELECT * FROM favorites ORDER BY created_at DESC LIMIT ?",
                (limit * 2,),
            )

    seen = set()
    items = []
    for r in rows:
        d = _fav_row_to_dict(r)
        key = (d["media_type"], str(d["content_id"]))
        if key not in seen:
            seen.add(key)
            items.append(d)
            if len(items) >= limit:
                break
    return items


def is_favorite(content_type: str, content_id: str, user_id: int = 0) -> bool:
    c_type = "movie" if (content_type or "").strip().lower() in ("movie", "film") else "tv"
    db_id = make_fav_id(c_type, content_id, user_id)
    guest_id = make_fav_id(c_type, content_id, 0)
    row = db.query_one(
        """
        SELECT 1 FROM favorites 
        WHERE id = ? OR id = ? OR (media_type = ? AND content_id = ? AND (user_id = ? OR user_id = 0))
        LIMIT 1
        """,
        (db_id, guest_id, c_type, str(content_id), user_id),
    )
    return row is not None


def add_favorite(
    media_type: str,
    content_id: str,
    title: str,
    slug: str = "",
    poster: Optional[str] = None,
    year: Optional[str] = None,
    score: Optional[str] = None,
    plot: Optional[str] = None,
    user_id: int = 0,
) -> dict:
    c_type = "movie" if (media_type or "").strip().lower() in ("movie", "film") else "tv"
    db_id = make_fav_id(c_type, content_id, user_id)
    now = datetime.now(timezone.utc).isoformat()

    with db.tx() as conn:
        conn.execute(
            """
            INSERT INTO favorites (
                id, user_id, media_type, content_id, slug, title, poster, year, score, plot, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                slug = CASE WHEN excluded.slug != '' THEN excluded.slug ELSE favorites.slug END,
                title = excluded.title,
                poster = COALESCE(excluded.poster, favorites.poster),
                year = COALESCE(excluded.year, favorites.year),
                score = COALESCE(excluded.score, favorites.score),
                plot = COALESCE(excluded.plot, favorites.plot)
            """,
            (
                db_id,
                user_id,
                c_type,
                str(content_id),
                slug or "",
                title,
                poster,
                str(year) if year is not None else None,
                str(score) if score is not None else None,
                plot,
                now,
            ),
        )
    logger.info("Added favorite: %s (user_id=%d, type=%s)", title, user_id, c_type)
    return {"status": "ok", "favorited": True, "id": db_id}


def remove_favorite(media_type: str, content_id: str, user_id: int = 0) -> bool:
    c_type = "movie" if (media_type or "").strip().lower() in ("movie", "film") else "tv"
    db_id = make_fav_id(c_type, content_id, user_id)
    guest_id = make_fav_id(c_type, content_id, 0)

    with db.tx() as conn:
        conn.execute(
            """
            DELETE FROM favorites 
            WHERE id = ? OR id = ? OR (media_type = ? AND content_id = ? AND (user_id = ? OR user_id = 0))
            """,
            (db_id, guest_id, c_type, str(content_id), user_id),
        )
    logger.info("Removed favorite: %s:%s (user_id=%d)", c_type, content_id, user_id)
    return True
