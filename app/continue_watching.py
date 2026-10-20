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


def _record_watch_history(
    user_id: int,
    content_type: str,
    content_id: str,
    slug: str,
    title: str,
    poster: Optional[str],
    position_seconds: float,
    duration_seconds: float,
    percentage: int,
    is_finished: bool,
    now: str,
):
    db_id = make_db_id(content_type, content_id, user_id)
    try:
        with db.tx() as conn:
            conn.execute(
                """
                INSERT INTO watch_history (
                    id, user_id, content_type, content_id, slug, title, poster,
                    last_position_seconds, duration_seconds, max_percentage,
                    completed, episodes_watched, last_watched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id = excluded.user_id,
                    content_type = excluded.content_type,
                    content_id = excluded.content_id,
                    slug = CASE WHEN excluded.slug != '' THEN excluded.slug ELSE watch_history.slug END,
                    title = excluded.title,
                    poster = COALESCE(excluded.poster, watch_history.poster),
                    last_position_seconds = excluded.last_position_seconds,
                    duration_seconds = excluded.duration_seconds,
                    max_percentage = MAX(watch_history.max_percentage, excluded.max_percentage),
                    completed = MAX(watch_history.completed, excluded.completed),
                    episodes_watched = watch_history.episodes_watched + CASE WHEN excluded.completed = 1 OR excluded.max_percentage >= 70 THEN 1 ELSE 0 END,
                    last_watched_at = excluded.last_watched_at
                """,
                (
                    db_id,
                    user_id,
                    content_type,
                    str(content_id),
                    slug or "",
                    title,
                    poster,
                    position_seconds,
                    duration_seconds,
                    percentage,
                    1 if is_finished else 0,
                    now,
                ),
            )
    except Exception as e:
        logger.warning("Failed to record watch history for %s: %s", db_id, e)


def get_recommendation_candidates(user_id: int = 0, content_type: Optional[str] = None, limit: int = 5) -> list[dict]:
    """Retrieve top engaged titles for recommendation generation.

    Prioritizes:
    1. Finished titles (completed=1 or max_percentage >= 80)
    2. Binged shows (episodes_watched >= 2 or high progress)
    3. Highly engaged in-progress titles (max_percentage >= 40)
    4. Explicit requests / downloads from jf_request
    """
    c_type = (content_type or "").strip().lower()
    if c_type in ("movie", "film"):
        c_type = "movie"
    elif c_type in ("tv", "series"):
        c_type = "tv"
    else:
        c_type = None

    candidates = []
    seen_keys = set()

    # 1. From watch_history
    try:
        if c_type:
            rows = db.query(
                """
                SELECT content_type, content_id, slug, title, poster, max_percentage, completed, episodes_watched, last_watched_at
                FROM watch_history
                WHERE user_id = ? AND content_type = ?
                ORDER BY completed DESC, (max_percentage >= 70) DESC, episodes_watched DESC, max_percentage DESC, last_watched_at DESC
                LIMIT ?
                """,
                (user_id, c_type, limit * 2),
            )
        else:
            rows = db.query(
                """
                SELECT content_type, content_id, slug, title, poster, max_percentage, completed, episodes_watched, last_watched_at
                FROM watch_history
                WHERE user_id = ?
                ORDER BY completed DESC, (max_percentage >= 70) DESC, episodes_watched DESC, max_percentage DESC, last_watched_at DESC
                LIMIT ?
                """,
                (user_id, limit * 2),
            )
        for r in rows:
            key = (r["content_type"], str(r["content_id"]))
            if key not in seen_keys:
                seen_keys.add(key)
                candidates.append({
                    "content_type": r["content_type"],
                    "content_id": r["content_id"],
                    "slug": r["slug"] or "",
                    "title": r["title"],
                    "poster": r["poster"],
                    "completed": bool(r["completed"]),
                    "percentage": int(r["max_percentage"] or 0),
                })
    except Exception as e:
        logger.warning("Error querying watch_history: %s", e)

    if len(candidates) >= limit:
        return candidates[:limit]

    # 2. Fallback to continue_watching
    try:
        if c_type:
            cw_rows = db.query(
                """
                SELECT content_type, content_id, slug, title, poster, position_seconds, duration_seconds
                FROM continue_watching
                WHERE user_id = ? AND content_type = ?
                ORDER BY (position_seconds / CASE WHEN duration_seconds > 0 THEN duration_seconds ELSE 1 END) DESC, updated_at DESC
                LIMIT ?
                """,
                (user_id, c_type, limit * 2),
            )
        else:
            cw_rows = db.query(
                """
                SELECT content_type, content_id, slug, title, poster, position_seconds, duration_seconds
                FROM continue_watching
                WHERE user_id = ?
                ORDER BY (position_seconds / CASE WHEN duration_seconds > 0 THEN duration_seconds ELSE 1 END) DESC, updated_at DESC
                LIMIT ?
                """,
                (user_id, limit * 2),
            )
        for r in cw_rows:
            c_kind = "movie" if (r["content_type"] or "").strip().lower() in ("movie", "film") else "tv"
            key = (c_kind, str(r["content_id"]))
            if key not in seen_keys:
                seen_keys.add(key)
                dur = float(r["duration_seconds"] or 0)
                pos = float(r["position_seconds"] or 0)
                pct = int(round((pos / dur) * 100)) if dur > 0 else 0
                candidates.append({
                    "content_type": c_kind,
                    "content_id": r["content_id"],
                    "slug": r["slug"] or "",
                    "title": r["title"],
                    "poster": r["poster"],
                    "completed": False,
                    "percentage": pct,
                })
    except Exception as e:
        logger.warning("Error querying continue_watching for recommendations: %s", e)

    if len(candidates) >= limit:
        return candidates[:limit]

    # 3. Fallback to jf_request
    try:
        req_rows = db.query(
            """
            SELECT media_type, external_id, slug, title, poster
            FROM jf_request
            WHERE requested_by = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit * 2),
        )
        for r in req_rows:
            c_kind = "movie" if (r["media_type"] or "").strip().lower() in ("film", "movie") else "tv"
            if c_type and c_kind != c_type:
                continue
            key = (c_kind, str(r["external_id"]))
            if key not in seen_keys:
                seen_keys.add(key)
                candidates.append({
                    "content_type": c_kind,
                    "content_id": r["external_id"],
                    "slug": r["slug"] or "",
                    "title": r["title"],
                    "poster": r["poster"],
                    "completed": True,
                    "percentage": 100,
                })
    except Exception as e:
        logger.warning("Error querying jf_request for recommendations: %s", e)

    return candidates[:limit]


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
    pct = int(min(100, max(0, round((pos / dur) * 100)))) if dur > 0 else 0
    now = datetime.now(timezone.utc).isoformat()

    # Finished condition: if >= 95% watched or fewer than 20 seconds remaining (with at least 1 min duration)
    is_finished = dur > 60 and (pos / dur >= 0.95 or (dur - pos) <= 20)

    # If poster is not supplied, keep previous poster if existing
    if not poster:
        existing = db.query_one("SELECT poster FROM continue_watching WHERE id = ?", (db_id,))
        if existing and existing["poster"]:
            poster = existing["poster"]

    # Record into permanent watch history (preserves completion & engagement)
    _record_watch_history(
        user_id=user_id,
        content_type=c_type,
        content_id=str(content_id),
        slug=slug or "",
        title=title,
        poster=poster,
        position_seconds=pos,
        duration_seconds=dur,
        percentage=pct,
        is_finished=is_finished,
        now=now,
    )

    if is_finished:
        delete_item(c_type, content_id, user_id)
        return {"status": "finished", "deleted": True}

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

