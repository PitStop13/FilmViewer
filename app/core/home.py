"""The shelves StreamingCommunity puts on its own front page and catalogs.

What the panel shows before anything is typed: trending, top 10,
film del momento, nuove uscite, serie TV più viste, serie TV più votate, etc.
"""

import json
import logging
import threading
import time

from bs4 import BeautifulSoup

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
    """The home page's own sliders: trending, recently added, today's top ten."""
    props = page.fetch_page_props(f"https://{domain}/it")
    shelves = []
    for slider in props.get("sliders") or []:
        key = slider.get("name") or slider.get("label")
        if not key:
            continue
        items = [t for t in (page.normalize_title(raw)
                             for raw in (slider.get("titles") or [])[:_SHELF_CAP]) if t]
        if items:
            shelves.append(_shelf("streamingcommunity", key, items,
                                  fallback=slider.get("label")))
    return shelves


# ── AnimeUnity ────────────────────────────────────────────────────────────────

def _attr_json(soup, attribute: str, element: str | None = None):
    """One element attribute carrying escaped JSON, decoded.

    BeautifulSoup unescapes the attribute itself, so there is no
    ``html.unescape()`` here — the payload is escaped exactly once, and a second
    pass would corrupt any ``&amp;amp;`` inside it.
    """
    node = soup.find(element, attrs={attribute: True}) if element else None
    if node is None:
        node = soup.find(attrs={attribute: True})
    if node is None:
        return None
    try:
        return json.loads(node[attribute])
    except Exception as exc:
        logger.warning("AnimeUnity %s attribute could not be read: %s", attribute, exc)
        return None


def _au_shelves(domain: str | None = None) -> list[dict]:
    """The home page's own lists: the latest episodes, and the featured carousel.

    Both ride in element attributes as escaped JSON rather than in an API.
    """
    from app.core import animeunity

    try:
        soup = BeautifulSoup(animeunity.fetch_home_html(domain), "html.parser")
    except Exception as exc:
        logger.warning("AnimeUnity fetch home error: %s", exc)
        return []

    latest_raw = (_attr_json(soup, "items-json") or {}).get("data") or []
    # Two new episodes of the same series are two rows and one card.
    latest, seen = [], set()
    for row in latest_raw:
        item = animeunity.normalize_title(row.get("anime") or {})
        if item and item["id"] not in seen:
            seen.add(item["id"])
            latest.append(item)

    featured_raw = _attr_json(soup, "animes", element="the-carousel") or []
    featured = [t for t in (animeunity.normalize_title(r) for r in featured_raw) if t]

    shelves = []
    for key, items in (("latest_episodes", latest), ("featured", featured)):
        if items:
            shelves.append(_shelf("animeunity", key, items[:_SHELF_CAP]))
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
    key = _cache_key(source, domain)
    hit = _cached(key)
    if hit is not None:
        return hit

    try:
        if source == "animeunity":
            result = _au_shelves(domain)
        elif source == "streamingcommunity":
            result = _sc_shelves(domain)
        else:
            result = []
    except Exception:
        logger.exception("Cannot read the front page of %s", source)
        return []

    if result:
        _store(key, result)
    return result
