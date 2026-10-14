"""The shelves StreamingCommunity puts on its own front page and catalogs.

What the panel shows before anything is typed: trending, top 10,
film del momento, nuove uscite, serie TV più viste, serie TV più votate, etc.
"""

import concurrent.futures
import logging
import threading
import time

from app.core import page

logger = logging.getLogger(__name__)

# A "trending" shelf fifteen minutes stale is indistinguishable from a fresh
# one; an hour is not.
_TTL = 15 * 60

# Only two keys are ever live. The bound exists so a pathological run of domain
# rotations cannot grow the dict.
_MAX_ENTRIES = 8

# How many titles of a shelf are worth rendering.
_SHELF_CAP = 30

_cache: dict[tuple, tuple[float, list]] = {}
_cache_lock = threading.Lock()


def _now() -> float:
    """Wall clock, indirected so tests can expire an entry without sleeping."""
    return time.time()


_LABELS = {
    ("streamingcommunity", "trending"): "Di tendenza",
    ("streamingcommunity", "latest"): "Aggiunti di recente",
    ("streamingcommunity", "top10"): "Top 10 di oggi",
    ("streamingcommunity", "movie_views"): "Film del momento e più visti",
    ("streamingcommunity", "movie_latest"): "Nuove uscite Film",
    ("streamingcommunity", "movie_top"): "Film più votati",
    ("streamingcommunity", "tv_views"): "Serie TV più viste",
    ("streamingcommunity", "tv_latest"): "Nuove serie TV",
    ("streamingcommunity", "tv_top"): "Serie TV più votate",
    ("animeunity", "latest_episodes"): "Ultimi episodi",
    ("animeunity", "featured"): "In evidenza",
}

_CATEGORIES = {
    "trending": "all",
    "top10": "all",
    "latest": "all",
    "movie_views": "movie",
    "movie_latest": "movie",
    "movie_top": "movie",
    "tv_views": "tv",
    "tv_latest": "tv",
    "tv_top": "tv",
}


def _cache_key(source: str, host: str) -> tuple:
    """Keyed on the host, not just the source."""
    return (source, host)


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

def _sc_shelves(domain: str) -> list[dict]:
    """The home page's own sliders plus subdivided Film and Serie TV archive shelves."""
    def fetch_home_sliders():
        try:
            props = page.fetch_page_props(f"https://{domain}/it")
            res = []
            for slider in props.get("sliders") or []:
                key = slider.get("name") or slider.get("label")
                if not key:
                    continue
                items = [t for t in (page.normalize_title(raw)
                                     for raw in (slider.get("titles") or [])[:_SHELF_CAP]) if t]
                if items:
                    res.append((key, items, slider.get("label")))
            return res
        except Exception as e:
            logger.warning("Failed to fetch home sliders: %s", e)
            return []

    def fetch_archive(key: str, media_type: str, sort: str):
        try:
            items = page.browse_archive(domain, media_type=media_type, sort=sort)[:_SHELF_CAP]
            return (key, items)
        except Exception as e:
            logger.warning("Failed to fetch archive shelf %s: %s", key, e)
            return (key, [])

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        f_home = executor.submit(fetch_home_sliders)
        f_mv = executor.submit(fetch_archive, "movie_views", "movie", "views")
        f_ml = executor.submit(fetch_archive, "movie_latest", "movie", "created_at")
        f_mt = executor.submit(fetch_archive, "movie_top", "movie", "score")
        f_tv = executor.submit(fetch_archive, "tv_views", "tv", "views")
        f_tl = executor.submit(fetch_archive, "tv_latest", "tv", "created_at")
        f_tt = executor.submit(fetch_archive, "tv_top", "tv", "score")

        home_sliders = f_home.result()
        archive_results = [
            f_mv.result(), f_ml.result(), f_mt.result(),
            f_tv.result(), f_tl.result(), f_tt.result(),
        ]

    shelves = []
    # 1. Sliders from home page (trending, top10, etc.)
    for key, items, fallback in home_sliders:
        if items:
            shelves.append(_shelf("streamingcommunity", key, items, fallback=fallback))

    # 2. Archive shelves subdivided by Film and Serie TV
    for key, items in archive_results:
        if items:
            shelves.append(_shelf("streamingcommunity", key, items))

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


def shelves(source: str, domain: str) -> list[dict]:
    """The front-page shelves for *source*, cached for a quarter of an hour."""
    if source == "animeunity":
        return []

    key = _cache_key(source, domain)
    hit = _cached(key)
    if hit is not None:
        return hit

    try:
        result = _sc_shelves(domain)
    except Exception:
        logger.exception("Cannot read the front page of %s", source)
        return []

    if result:
        _store(key, result)
    return result
