"""The shelves StreamingCommunity puts on its own front page and catalogs.

What the panel shows before anything is typed: trending, top 10,
film del momento, nuove uscite, serie TV più viste, serie TV più votate, etc.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import threading
import time

from app.core import page

logger = logging.getLogger(__name__)

# A "trending" shelf fifteen minutes stale is indistinguishable from a fresh
# one; an hour is not.
_TTL = 15 * 60

# Sized so all categories (all, movie, tv) and domain rotations fit comfortably.
_MAX_ENTRIES = 24

# How many titles of a shelf are worth rendering.
_SHELF_CAP = 35

_cache: dict[tuple, tuple[float, list]] = {}
_cache_lock = threading.Lock()


def _now() -> float:
    """Wall clock, indirected so tests can expire an entry without sleeping."""
    return time.time()


_LABELS = {
    ("streamingcommunity", "trending"): "Di tendenza",
    ("streamingcommunity", "latest"): "Aggiunti di recente",
    ("streamingcommunity", "top10"): "Top 10 di oggi",
    ("streamingcommunity", "movie_views"): "I più visti e popolari",
    ("streamingcommunity", "movie_latest"): "Nuove uscite Film",
    ("streamingcommunity", "movie_action"): "Film d'Azione & Avventura",
    ("streamingcommunity", "movie_comedy"): "Commedie & Risate",
    ("streamingcommunity", "movie_animation"): "Animazione & Famiglia",
    ("streamingcommunity", "movie_crime"): "Thriller & Crime",
    ("streamingcommunity", "movie_drama"): "Grandi Drammi & Storie",
    ("streamingcommunity", "movie_top"): "Film più votati",
    ("streamingcommunity", "tv_views"): "Serie TV più viste",
    ("streamingcommunity", "tv_latest"): "Nuove serie TV",
    ("streamingcommunity", "tv_action"): "Serie Action & Adventure",
    ("streamingcommunity", "tv_drama"): "Serie TV Drammatiche",
    ("streamingcommunity", "tv_animation"): "Serie Animate",
    ("streamingcommunity", "tv_top"): "Serie TV più votate",
}

_CATEGORIES = {
    "trending": "all",
    "top10": "all",
    "latest": "all",
    "movie_views": "movie",
    "movie_latest": "movie",
    "movie_action": "movie",
    "movie_comedy": "movie",
    "movie_animation": "movie",
    "movie_crime": "movie",
    "movie_drama": "movie",
    "movie_top": "movie",
    "tv_views": "tv",
    "tv_latest": "tv",
    "tv_action": "tv",
    "tv_drama": "tv",
    "tv_animation": "tv",
    "tv_top": "tv",
}


def _cache_key(source: str, host: str, category: str | None = None) -> tuple:
    """Keyed on source, host, and optional category."""
    return (source, host, category or "default")


def _cached(key: tuple) -> list | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < _now():
            _cache.pop(key, None)
            return None
        return value


def _store(key: tuple, value: list) -> None:
    with _cache_lock:
        if len(_cache) >= _MAX_ENTRIES:
            now = _now()
            for stale in [k for k, (exp, _) in _cache.items() if exp < now]:
                _cache.pop(stale, None)
            if len(_cache) >= _MAX_ENTRIES:
                _cache.pop(next(iter(_cache)), None)
        _cache[key] = (_now() + _TTL, value)


def clear_cache(source: str | None = None) -> None:
    """Drop cached shelves, for one source or all of them."""
    with _cache_lock:
        if source is None:
            _cache.clear()
            return
        for key in [k for k in _cache if k[0] == source]:
            _cache.pop(key, None)


# ── StreamingCommunity ────────────────────────────────────────────────────────

def _sc_archive_shelf(domain: str, key: str, params: dict, category: str) -> dict | None:
    try:
        props = page.fetch_page_props(f"https://{domain}/it/archive", params=params, timeout=12)
        raw_titles = props.get("titles") or []
        items = [t for t in (page.normalize_title(raw) for raw in raw_titles[:_SHELF_CAP]) if t]
        if items:
            return _shelf("streamingcommunity", key, items)
    except Exception as e:
        logger.warning("Failed to fetch archive shelf %s: %s", key, e)
    return None


def _sc_shelves(domain: str, category: str | None = None) -> list[dict]:
    """The home page and catalog shelves, enriched by category."""
    shelves = []

    # Category "movie": full dedicated movie catalog
    if category == "movie":
        queries = [
            ("movie_views", {"type": "movie", "sort": "views"}),
            ("movie_latest", {"type": "movie", "sort": "release_date"}),
            ("movie_action", {"type": "movie", "genre[0]": 4}),
            ("movie_comedy", {"type": "movie", "genre[0]": 12}),
            ("movie_animation", {"type": "movie", "genre[0]": 19}),
            ("movie_crime", {"type": "movie", "genre[0]": 2}),
            ("movie_drama", {"type": "movie", "genre[0]": 1}),
        ]
        with ThreadPoolExecutor(max_workers=7) as executor:
            futures = [
                executor.submit(_sc_archive_shelf, domain, key, params, "movie")
                for key, params in queries
            ]
            for fut in futures:
                res = fut.result()
                if res:
                    shelves.append(res)
        return shelves

    # Category "tv": full dedicated TV catalog
    if category == "tv":
        queries = [
            ("tv_views", {"type": "tv", "sort": "views"}),
            ("tv_latest", {"type": "tv", "sort": "release_date"}),
            ("tv_action", {"type": "tv", "genre[0]": 13}),
            ("tv_drama", {"type": "tv", "genre[0]": 1}),
            ("tv_animation", {"type": "tv", "genre[0]": 19}),
        ]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(_sc_archive_shelf, domain, key, params, "tv")
                for key, params in queries
            ]
            for fut in futures:
                res = fut.result()
                if res:
                    shelves.append(res)
        return shelves

    # Default / "all": fetch main page sliders (trending, latest, top10)
    props = page.fetch_page_props(f"https://{domain}/it")
    for slider in props.get("sliders") or []:
        key = slider.get("name") or slider.get("label")
        if not key:
            continue
        items = [t for t in (page.normalize_title(raw)
                             for raw in (slider.get("titles") or [])[:_SHELF_CAP]) if t]
        if items:
            shelves.append(_shelf("streamingcommunity", key, items,
                                  fallback=slider.get("label")))

    # In "all" mode, enrich with top movie and series rails
    if category == "all":
        extra_queries = [
            ("movie_views", {"type": "movie", "sort": "views"}, "movie"),
            ("tv_views", {"type": "tv", "sort": "views"}, "tv"),
            ("movie_action", {"type": "movie", "genre": 4}, "movie"),
            ("movie_comedy", {"type": "movie", "genre": 12}, "movie"),
        ]
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(_sc_archive_shelf, domain, key, params, cat)
                for key, params, cat in extra_queries
            ]
            for fut in futures:
                res = fut.result()
                if res:
                    shelves.append(res)

    return shelves


# ── Assembly ──────────────────────────────────────────────────────────────────

def _shelf(source: str, key: str, items: list, fallback: str | None = None) -> dict:
    title = _LABELS.get((source, key)) or _LABELS.get(key) or fallback or key
    category = _CATEGORIES.get(key, "all")
    return {
        "key": key,
        "title": title,
        "category": category,
        "items": items,
    }


def shelves(source: str, domain: str, category: str | None = None) -> list[dict]:
    """The front-page and catalog shelves for *source*, cached for 15 minutes."""
    if source != "streamingcommunity":
        return []

    key = _cache_key(source, domain, category)
    hit = _cached(key)
    if hit is not None:
        return hit

    try:
        result = _sc_shelves(domain, category)
    except Exception:
        logger.exception("Cannot read the front page of %s", source)
        return []

    if result:
        _store(key, result)
    return result

