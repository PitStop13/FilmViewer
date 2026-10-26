"""The shelves StreamingCommunity puts on its own front page and catalogs.

What the panel shows before anything is typed: trending, top 10,
film del momento, nuove uscite, serie TV più viste, serie TV più votate, etc.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import random
import threading
import time

from app import continue_watching as cw_service
from app.core import page

logger = logging.getLogger(__name__)

# A "trending" shelf fifteen minutes stale is indistinguishable from a fresh
# one; an hour is not.
_TTL = 15 * 60

# Sized so all categories (all, movie, tv) and domain rotations fit comfortably.
_MAX_ENTRIES = 48

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
    ("streamingcommunity", "movie_views"): "Film più visti e popolari",
    ("streamingcommunity", "movie_latest"): "Nuove uscite Film",
    ("streamingcommunity", "movie_top"): "Film più acclamati dalla critica",
    ("streamingcommunity", "movie_gems"): "🎲 Gemme dal catalogo Film",
    ("streamingcommunity", "movie_action"): "Film d'Azione & Adrenalina",
    ("streamingcommunity", "movie_comedy"): "Commedie & Risate",
    ("streamingcommunity", "movie_animation"): "Animazione & Grandi Capolavori",
    ("streamingcommunity", "movie_crime"): "Crime, Mafia & Gangster",
    ("streamingcommunity", "movie_drama"): "Grandi Drammi & Emozioni",
    ("streamingcommunity", "movie_scifi"): "Fantascienza & Futuro",
    ("streamingcommunity", "movie_thriller"): "Thriller & Suspense ad alta tensione",
    ("streamingcommunity", "movie_fantasy"): "Fantasy & Mondi Immaginari",
    ("streamingcommunity", "movie_horror"): "Horror & Brividi",
    ("streamingcommunity", "movie_adventure"): "Avventura & Grandi Esplorazioni",
    ("streamingcommunity", "movie_mystery"): "Mistero & Investigazioni",
    ("streamingcommunity", "movie_history"): "Guerra & Film Storici",
    ("streamingcommunity", "movie_western"): "Western & Frontiera",
    ("streamingcommunity", "movie_doc"): "Documentari Straordinari",
    ("streamingcommunity", "movie_romance"): "Film Romantici & Passione",
    ("streamingcommunity", "tv_views"): "Serie TV più viste e popolari",
    ("streamingcommunity", "tv_latest"): "Nuove serie TV",
    ("streamingcommunity", "tv_top"): "Serie TV più acclamate dalla critica",
    ("streamingcommunity", "tv_gems"): "🎲 Gemme dal catalogo Serie TV",
    ("streamingcommunity", "tv_action"): "Serie TV Action & Adventure",
    ("streamingcommunity", "tv_drama"): "Grandi Serie TV Drammatiche",
    ("streamingcommunity", "tv_animation"): "Serie Animate & Anime",
    ("streamingcommunity", "tv_scifi"): "Serie TV Sci-Fi & Fantasy",
    ("streamingcommunity", "tv_crime"): "Serie TV Crime & Poliziesche",
    ("streamingcommunity", "tv_comedy"): "Serie TV Comedy & Sitcom",
    ("streamingcommunity", "tv_mystery"): "Serie TV Mistero & Thriller",
    ("streamingcommunity", "tv_doc"): "Docuserie & Inchieste",
    ("streamingcommunity", "tv_kdrama"): "K-Drama & Serie Coreane",
    ("streamingcommunity", "tv_reality"): "Reality & Show TV",
    ("streamingcommunity", "all_surprise"): "🎲 Titoli a sorpresa da non perdere",
    ("streamingcommunity", "all_top_critics"): "I capolavori più votati",
}

_CATEGORIES = {
    "trending": "all",
    "top10": "all",
    "latest": "all",
    "all_surprise": "all",
    "all_top_critics": "all",
    "movie_views": "movie",
    "movie_latest": "movie",
    "movie_top": "movie",
    "movie_gems": "movie",
    "movie_action": "movie",
    "movie_comedy": "movie",
    "movie_animation": "movie",
    "movie_crime": "movie",
    "movie_drama": "movie",
    "movie_scifi": "movie",
    "movie_thriller": "movie",
    "movie_fantasy": "movie",
    "movie_horror": "movie",
    "movie_adventure": "movie",
    "movie_mystery": "movie",
    "movie_history": "movie",
    "movie_western": "movie",
    "movie_doc": "movie",
    "movie_romance": "movie",
    "tv_views": "tv",
    "tv_latest": "tv",
    "tv_top": "tv",
    "tv_gems": "tv",
    "tv_action": "tv",
    "tv_drama": "tv",
    "tv_animation": "tv",
    "tv_scifi": "tv",
    "tv_crime": "tv",
    "tv_comedy": "tv",
    "tv_mystery": "tv",
    "tv_doc": "tv",
    "tv_kdrama": "tv",
    "tv_reality": "tv",
}

_MOVIE_GENRE_POOL = [
    ("movie_scifi", "Fantascienza & Futuro", 10),
    ("movie_thriller", "Thriller & Suspense ad alta tensione", 5),
    ("movie_action", "Film d'Azione & Adrenalina", 4),
    ("movie_comedy", "Commedie & Risate", 12),
    ("movie_animation", "Animazione & Grandi Capolavori", 19),
    ("movie_crime", "Crime, Mafia & Gangster", 2),
    ("movie_drama", "Grandi Drammi & Emozioni", 1),
    ("movie_fantasy", "Fantasy & Mondi Immaginari", 8),
    ("movie_horror", "Horror & Brividi", 7),
    ("movie_adventure", "Avventura & Grandi Esplorazioni", 11),
    ("movie_mystery", "Mistero & Investigazioni", 6),
    ("movie_history", "Guerra & Film Storici", 9),
    ("movie_western", "Western & Frontiera", 20),
    ("movie_doc", "Documentari Straordinari", 24),
    ("movie_romance", "Film Romantici & Passione", 15),
]

_TV_GENRE_POOL = [
    ("tv_scifi", "Serie TV Sci-Fi & Fantasy", 3),
    ("tv_crime", "Serie TV Crime & Poliziesche", 2),
    ("tv_action", "Serie TV Action & Adventure", 13),
    ("tv_drama", "Grandi Serie TV Drammatiche", 1),
    ("tv_comedy", "Serie TV Comedy & Sitcom", 12),
    ("tv_animation", "Serie Animate & Anime", 19),
    ("tv_mystery", "Serie TV Mistero & Thriller", 6),
    ("tv_kdrama", "K-Drama & Serie Coreane", 26),
    ("tv_doc", "Docuserie & Inchieste", 24),
    ("tv_reality", "Reality & Show TV", 18),
]


def _cache_key(source: str, host: str, category: str | None = None, user_id: int = 0) -> tuple:
    """Keyed on source, host, optional category, and user_id."""
    return (source, host, category or "default", user_id)


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


_ARCHIVE_CACHE: dict[tuple, tuple[float, dict]] = {}
_ARCHIVE_LOCK = threading.Lock()
_ARCHIVE_TTL = 30 * 60  # 30 minutes

_REC_CACHE: dict[tuple, tuple[float, dict]] = {}
_REC_LOCK = threading.Lock()
_REC_TTL = 6 * 3600  # 6 hours


def clear_cache(source: str | None = None) -> None:
    """Drop cached shelves, for one source or all of them."""
    with _cache_lock:
        if source is None:
            _cache.clear()
        else:
            for key in [k for k in _cache if k[0] == source]:
                _cache.pop(key, None)
    with _ARCHIVE_LOCK:
        _ARCHIVE_CACHE.clear()
    with _REC_LOCK:
        _REC_CACHE.clear()


# ── StreamingCommunity ────────────────────────────────────────────────────────

def _sc_archive_shelf(domain: str, key: str, params: dict, category: str) -> dict | None:
    cache_k = (domain, key, tuple(sorted(params.items())))
    now = _now()
    with _ARCHIVE_LOCK:
        if cache_k in _ARCHIVE_CACHE:
            exp, val = _ARCHIVE_CACHE[cache_k]
            if exp > now:
                return val
            _ARCHIVE_CACHE.pop(cache_k, None)

    try:
        props = page.fetch_page_props(f"https://{domain}/it/archive", params=params, timeout=8)
        raw_titles = props.get("titles") or []
        items = [t for t in (page.normalize_title(raw) for raw in raw_titles[:_SHELF_CAP]) if t]
        if items:
            shelf_obj = _shelf("streamingcommunity", key, items)
            with _ARCHIVE_LOCK:
                if len(_ARCHIVE_CACHE) > 150:
                    _ARCHIVE_CACHE.clear()
                _ARCHIVE_CACHE[cache_k] = (now + _ARCHIVE_TTL, shelf_obj)
            return shelf_obj
    except Exception as e:
        logger.warning("Failed to fetch archive shelf %s: %s", key, e)
    return None


def _sc_fetch_recommendations_for_title(domain: str, candidate: dict) -> dict | None:
    """Fetch similar titles based on a watched candidate title.

    Tries:
    1. The source's own 'related' slider (high quality recommendation pool)
    2. The source's own 'genre' slider
    3. Archive filtered by the title's primary genre
    """
    cid = candidate.get("content_id")
    slug = candidate.get("slug") or ""
    c_type = candidate.get("content_type") or "movie"
    title = candidate.get("title") or "questo titolo"
    if not cid:
        return None

    cache_k = (domain, str(cid))
    now = _now()
    with _REC_LOCK:
        if cache_k in _REC_CACHE:
            exp, val = _REC_CACHE[cache_k]
            if exp > now:
                return val
            _REC_CACHE.pop(cache_k, None)

    try:
        url = f"https://{domain}/it/titles/{cid}-{slug}" if slug else f"https://{domain}/it/titles/{cid}"
        props = page.fetch_page_props(url, timeout=8)

        # 1. Try 'related' slider
        for slider in props.get("sliders") or []:
            if slider.get("name") == "related":
                raw_titles = slider.get("titles") or []
                items = [
                    t for t in (page.normalize_title(raw) for raw in raw_titles)
                    if t and str(t.get("id")) != str(cid)
                ]
                if len(items) >= 4:
                    shelf_obj = _shelf(
                        "streamingcommunity",
                        f"rec_{c_type}_{cid}",
                        items[:_SHELF_CAP],
                        fallback=f"Perché hai guardato {title}",
                    )
                    with _REC_LOCK:
                        if len(_REC_CACHE) > 100:
                            _REC_CACHE.clear()
                        _REC_CACHE[cache_k] = (now + _REC_TTL, shelf_obj)
                    return shelf_obj

        # 2. Try 'genre' slider
        for slider in props.get("sliders") or []:
            if slider.get("name") == "genre":
                raw_titles = slider.get("titles") or []
                items = [
                    t for t in (page.normalize_title(raw) for raw in raw_titles)
                    if t and str(t.get("id")) != str(cid)
                ]
                if len(items) >= 4:
                    shelf_obj = _shelf(
                        "streamingcommunity",
                        f"rec_{c_type}_{cid}",
                        items[:_SHELF_CAP],
                        fallback=f"Perché hai guardato {title}",
                    )
                    with _REC_LOCK:
                        if len(_REC_CACHE) > 100:
                            _REC_CACHE.clear()
                        _REC_CACHE[cache_k] = (now + _REC_TTL, shelf_obj)
                    return shelf_obj

        # 3. Fallback: archive query for the primary genre
        genres = props.get("title", {}).get("genres") or []
        if genres and genres[0].get("id"):
            gid = genres[0]["id"]
            archive_props = page.fetch_page_props(
                f"https://{domain}/it/archive",
                params={"type": c_type, "genre[0]": gid, "sort": "views"},
                timeout=8,
            )
            raw_titles = archive_props.get("titles") or []
            items = [
                t for t in (page.normalize_title(raw) for raw in raw_titles)
                if t and str(t.get("id")) != str(cid)
            ]
            if items:
                shelf_obj = _shelf(
                    "streamingcommunity",
                    f"rec_{c_type}_{cid}",
                    items[:_SHELF_CAP],
                    fallback=f"Perché hai guardato {title}",
                )
                with _REC_LOCK:
                    if len(_REC_CACHE) > 100:
                        _REC_CACHE.clear()
                    _REC_CACHE[cache_k] = (now + _REC_TTL, shelf_obj)
                return shelf_obj
    except Exception as e:
        logger.warning("Failed to fetch recommendations for title %s: %s", cid, e)
    return None


def _sc_shelves(domain: str, category: str | None = None, user_id: int = 0) -> list[dict]:
    """The home page and catalog shelves, enriched by recommendations and dynamic rotation."""
    shelves = []

    # Category "movie": full dedicated movie catalog
    if category == "movie":
        core_queries = [
            ("movie_views", {"type": "movie", "sort": "views"}),
            ("movie_latest", {"type": "movie", "sort": "release_date"}),
        ]

        # Recommendation candidate (best single match)
        candidates = cw_service.get_recommendation_candidates(user_id=user_id, content_type="movie", limit=1)

        # Dynamic sample of genres for variety
        sampled_genres = random.sample(_MOVIE_GENRE_POOL, min(2, len(_MOVIE_GENRE_POOL)))
        genre_queries = [
            (key, {"type": "movie", "genre[0]": gid, "page": random.choice([1, 2])})
            for key, label, gid in sampled_genres
        ]

        with ThreadPoolExecutor(max_workers=5) as executor:
            core_futures = [
                executor.submit(_sc_archive_shelf, domain, key, params, "movie")
                for key, params in core_queries
            ]
            rec_futures = [
                executor.submit(_sc_fetch_recommendations_for_title, domain, cand)
                for cand in candidates
            ]
            genre_futures = [
                executor.submit(_sc_archive_shelf, domain, key, params, "movie")
                for key, params in genre_queries
            ]

            for fut in core_futures:
                res = fut.result()
                if res:
                    shelves.append(res)

            has_rec = False
            for fut in rec_futures:
                res = fut.result()
                if res:
                    shelves.append(res)
                    has_rec = True

            if not has_rec:
                gems_res = _sc_archive_shelf(
                    domain,
                    "movie_gems",
                    {"type": "movie", "sort": "views", "page": random.choice([2, 3])},
                    "movie",
                )
                if gems_res:
                    shelves.append(gems_res)

            for fut in genre_futures:
                res = fut.result()
                if res:
                    shelves.append(res)

        return shelves

    # Category "tv": full dedicated TV catalog
    if category == "tv":
        core_queries = [
            ("tv_views", {"type": "tv", "sort": "views"}),
            ("tv_latest", {"type": "tv", "sort": "release_date"}),
        ]

        # Recommendation candidate
        candidates = cw_service.get_recommendation_candidates(user_id=user_id, content_type="tv", limit=1)

        # Dynamic sample of TV genres
        sampled_genres = random.sample(_TV_GENRE_POOL, min(2, len(_TV_GENRE_POOL)))
        genre_queries = [
            (key, {"type": "tv", "genre[0]": gid, "page": random.choice([1, 2])})
            for key, label, gid in sampled_genres
        ]

        with ThreadPoolExecutor(max_workers=5) as executor:
            core_futures = [
                executor.submit(_sc_archive_shelf, domain, key, params, "tv")
                for key, params in core_queries
            ]
            rec_futures = [
                executor.submit(_sc_fetch_recommendations_for_title, domain, cand)
                for cand in candidates
            ]
            genre_futures = [
                executor.submit(_sc_archive_shelf, domain, key, params, "tv")
                for key, params in genre_queries
            ]

            for fut in core_futures:
                res = fut.result()
                if res:
                    shelves.append(res)

            has_rec = False
            for fut in rec_futures:
                res = fut.result()
                if res:
                    shelves.append(res)
                    has_rec = True

            if not has_rec:
                gems_res = _sc_archive_shelf(
                    domain,
                    "tv_gems",
                    {"type": "tv", "sort": "views", "page": random.choice([2, 3])},
                    "tv",
                )
                if gems_res:
                    shelves.append(gems_res)

            for fut in genre_futures:
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

    # In "all" mode, enrich with top rails and recommendations (focused and fast)
    if category == "all":
        core_extra = [
            ("movie_views", {"type": "movie", "sort": "views"}, "movie"),
            ("tv_views", {"type": "tv", "sort": "views"}, "tv"),
        ]

        candidates = cw_service.get_recommendation_candidates(user_id=user_id, limit=1)

        with ThreadPoolExecutor(max_workers=3) as executor:
            core_futures = [
                executor.submit(_sc_archive_shelf, domain, key, params, cat)
                for key, params, cat in core_extra
            ]
            rec_futures = [
                executor.submit(_sc_fetch_recommendations_for_title, domain, cand)
                for cand in candidates
            ]

            for fut in core_futures:
                res = fut.result()
                if res:
                    shelves.append(res)

            for fut in rec_futures:
                res = fut.result()
                if res:
                    shelves.append(res)

    return shelves


# ── Assembly ──────────────────────────────────────────────────────────────────

def _shelf(source: str, key: str, items: list, fallback: str | None = None) -> dict:
    title = _LABELS.get((source, key)) or _LABELS.get(key) or fallback or key
    category = _CATEGORIES.get(key)
    if not category:
        if key.startswith("rec_movie") or key.startswith("movie_"):
            category = "movie"
        elif key.startswith("rec_tv") or key.startswith("tv_"):
            category = "tv"
        else:
            category = "all"
    return {
        "key": key,
        "title": title,
        "category": category,
        "items": items,
    }


def shelves(
    source: str,
    domain: str,
    category: str | None = None,
    user_id: int = 0,
    refresh: bool = False,
) -> list[dict]:
    """The front-page and catalog shelves for *source*, cached for 15 minutes."""
    if source != "streamingcommunity":
        return []

    key = _cache_key(source, domain, category, user_id)
    if not refresh:
        hit = _cached(key)
        if hit is not None:
            return hit
    else:
        with _cache_lock:
            _cache.pop(key, None)

    try:
        result = _sc_shelves(domain, category, user_id=user_id)
    except Exception:
        logger.exception("Cannot read the front page of %s", source)
        return []

    if result:
        _store(key, result)
    return result

