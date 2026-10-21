import asyncio
import logging
import os
import re
import threading
import time
from typing import Optional
from urllib.parse import parse_qs, quote_plus, unquote_plus, urljoin, urlparse, urlunparse
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests

from app.auth import models
from app.auth.deps import require
from app.auth.permissions import Permission
from app.config import configured_domain
from app.core.headers import get_headers
from app.core._shared import (
    _fetch_vixcloud_embed,
    _parse_content,
    _get_m3u8_url,
    _get_m3u8_key,
)
from app.core.film import _get_iframe as _get_film_iframe
from app.core.tv import (
    get_token as _get_tv_token,
    _get_iframe as _get_tv_iframe,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stream",
    tags=["stream"],
    dependencies=[
        Depends(
            require(
                Permission.VIEW_LIBRARY,
                Permission.REQUEST,
                Permission.DOWNLOAD,
                mode="or",
            )
        )
    ],
)

_STREAM_SESSIONS: dict[str, dict] = {}
_STREAM_SESSIONS_LOCK = threading.Lock()
_STREAM_TTL = 4 * 3600  # 4 hours

_SEGMENT_CACHE: dict[str, tuple[float, bytes]] = {}
_SEGMENT_CACHE_LOCK = threading.Lock()
_MAX_SEGMENTS_CACHE = 60
_SEGMENT_TTL = 600.0  # 10 minutes

_TV_DEFAULT_EP_CACHE: dict[str, tuple[str, str, str]] = {}
_TV_DEFAULT_EP_LOCK = threading.Lock()


def _create_stream_session(m3u8_url: str, referer: str, key_hex: Optional[str], meta: dict) -> str:
    token = uuid.uuid4().hex
    now = time.time()
    with _STREAM_SESSIONS_LOCK:
        expired = [k for k, v in _STREAM_SESSIONS.items() if v.get("expires_at", 0) < now]
        for k in expired:
            _STREAM_SESSIONS.pop(k, None)
        _STREAM_SESSIONS[token] = {
            "m3u8_url": m3u8_url,
            "referer": referer,
            "key_hex": key_hex,
            "meta": meta,
            "created_at": now,
            "expires_at": now + _STREAM_TTL,
        }
    return token


def _get_stream_session(token: str) -> Optional[dict]:
    now = time.time()
    with _STREAM_SESSIONS_LOCK:
        session = _STREAM_SESSIONS.get(token)
        if not session:
            return None
        if session.get("expires_at", 0) < now:
            _STREAM_SESSIONS.pop(token, None)
            return None
        return session


_http_session: Optional[requests.Session] = None
_http_session_lock = threading.Lock()


_ORIGINAL_REQUESTS_GET = requests.get


def _get_http_session() -> requests.Session:
    global _http_session
    with _http_session_lock:
        if _http_session is None:
            _http_session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=2)
            _http_session.mount("https://", adapter)
            _http_session.mount("http://", adapter)
        return _http_session


def _http_get(url: str, **kwargs):
    if requests.get is not _ORIGINAL_REQUESTS_GET:
        return requests.get(url, **kwargs)
    return _get_http_session().get(url, **kwargs)


def _make_abs_url(base_url: str, rel_url: str) -> str:
    abs_url = urljoin(base_url, rel_url)
    base_parts = urlparse(base_url)
    abs_parts = urlparse(abs_url)
    if not abs_parts.query and base_parts.query:
        abs_parts = abs_parts._replace(query=base_parts.query)
        return urlunparse(abs_parts)
    return abs_url


def _sc_domain() -> str:
    domain = configured_domain()
    if not domain:
        raise HTTPException(status_code=409, detail="Nessun dominio StreamingCommunity configurato")
    return domain


class StreamPrepareRequest(BaseModel):
    content_type: str
    id: str
    slug: Optional[str] = ""
    episode_id: Optional[str] = None
    episode_number: Optional[str] = None
    age: Optional[str] = None


@router.get("/watch-info")
async def get_watch_info(
    request: Request,
    content_type: str = Query(..., alias="content_type"),
    id: str = Query(...),
    slug: str = Query(""),
    episode_id: Optional[str] = Query(None),
    episode_number: Optional[str] = Query(None),
    age: Optional[str] = Query(None),
):
    """Provide direct watch URL and embed player URL for online streaming."""
    c_type = (content_type or "").lower().strip()

    if c_type in ("movie", "film"):
        domain = _sc_domain()
        watch_url = f"https://{domain}/it/watch/{id}"
        embed_url = f"https://{domain}/it/iframe/{id}"
        return {
            "content_type": "movie",
            "id": id,
            "watch_url": watch_url,
            "embed_url": embed_url,
            "source_name": "StreamingCommunity",
        }

    if c_type in ("tv", "series"):
        domain = _sc_domain()
        if episode_id:
            watch_url = f"https://{domain}/it/watch/{id}?e={episode_id}"
            embed_url = f"https://{domain}/it/iframe/{id}?episode_id={episode_id}"
        else:
            watch_url = f"https://{domain}/it/titles/{id}-{slug}" if slug else f"https://{domain}/it/watch/{id}"
            embed_url = f"https://{domain}/it/iframe/{id}"
        return {
            "content_type": "tv",
            "id": id,
            "episode_id": episode_id,
            "watch_url": watch_url,
            "embed_url": embed_url,
            "source_name": "StreamingCommunity",
        }

    raise HTTPException(status_code=400, detail=f"Tipo di contenuto non valido: {content_type}")


@router.post("/prepare")
async def prepare_stream(req: StreamPrepareRequest, request: Request):
    c_type = (req.content_type or "").lower().strip()

    domain = _sc_domain()


    def _resolve():
        if c_type in ("movie", "film"):
            embed_content, embed_referer = _get_film_iframe(int(req.id), domain)
            json_win_video, json_win_param = _parse_content(embed_content, embed_referer)
            m3u8_url = _get_m3u8_url(json_win_video, json_win_param)
            try:
                key_hex = _get_m3u8_key(json_win_video, json_win_param, embed_referer)
            except Exception as e:
                logger.warning("Could not pre-fetch key during prepare: %s", e)
                key_hex = None
            token = _create_stream_session(m3u8_url, embed_referer, key_hex, {
                "type": "movie", "id": req.id, "slug": req.slug
            })
            return token, None, None, None
        elif c_type in ("tv", "series"):
            episode_id = req.episode_id
            episode_num = req.episode_number
            resolved_title = None

            # 1. If no episode_id was passed, check if the user was already watching this series
            if not episode_id:
                user_id = getattr(request.state, "user_id", 0)
                try:
                    from app.continue_watching import get_continue_watching
                    cw_list = get_continue_watching(user_id=user_id)
                    found_cw = next((cw for cw in cw_list if str(cw.get("content_id")) == str(req.id) and cw.get("content_type") == "tv"), None)
                    if found_cw and found_cw.get("episode_id"):
                        episode_id = str(found_cw["episode_id"])
                        episode_num = str(found_cw.get("episode_number") or 1)
                        resolved_title = found_cw.get("episode_title")
                except Exception as ex:
                    logger.debug("Could not lookup continue watching for tv stream: %s", ex)

            # 2. Check in-memory default episode cache
            if not episode_id:
                with _TV_DEFAULT_EP_LOCK:
                    cached_ep = _TV_DEFAULT_EP_CACHE.get(str(req.id))
                    if cached_ep:
                        episode_id, episode_num, resolved_title = cached_ep

            # 3. If still no episode_id, auto-resolve Episode 1 from the title watch page
            if not episode_id:
                try:
                    import json
                    from bs4 import BeautifulSoup
                    watch_resp = _http_get(
                        f"https://{domain}/it/watch/{req.id}",
                        headers={"user-agent": get_headers()},
                        timeout=8,
                    )
                    if watch_resp.ok:
                        soup = BeautifulSoup(watch_resp.text, "lxml")
                        app_div = soup.find(id="app")
                        if app_div and app_div.get("data-page"):
                            p_data = json.loads(app_div["data-page"])
                            ep_data = p_data.get("props", {}).get("episode")
                            if ep_data and ep_data.get("id"):
                                episode_id = str(ep_data["id"])
                                episode_num = str(ep_data.get("number") or 1)
                                resolved_title = ep_data.get("name") or f"Episodio {episode_num}"
                                with _TV_DEFAULT_EP_LOCK:
                                    _TV_DEFAULT_EP_CACHE[str(req.id)] = (episode_id, episode_num, resolved_title)
                except Exception as ex:
                    logger.warning("Could not auto-resolve default episode from watch page: %s", ex)

            # 4. Fallback: query season 1
            if not episode_id:
                try:
                    from app.core.page import get_domain_version
                    from app.core.tv import get_info_season
                    version = get_domain_version(domain)
                    season_token = _get_tv_token(int(req.id), domain)
                    season_eps = get_info_season(int(req.id), req.slug or "series", domain, version, season_token, 1)
                    if season_eps and len(season_eps) > 0:
                        episode_id = str(season_eps[0]["id"])
                        episode_num = str(season_eps[0].get("n") or 1)
                        resolved_title = season_eps[0].get("name") or f"Episodio {episode_num}"
                        with _TV_DEFAULT_EP_LOCK:
                            _TV_DEFAULT_EP_CACHE[str(req.id)] = (episode_id, episode_num, resolved_title)
                except Exception as ex:
                    logger.warning("Could not auto-resolve season 1 episodes: %s", ex)

            if not episode_id:
                raise ValueError("Nessun episodio trovato per questa serie TV")

            sc_token = _get_tv_token(int(req.id), domain)
            embed_content, embed_referer = _get_tv_iframe(int(req.id), int(episode_id), domain, sc_token)
            json_win_video, json_win_param = _parse_content(embed_content, embed_referer)
            m3u8_url = _get_m3u8_url(json_win_video, json_win_param)
            try:
                key_hex = _get_m3u8_key(json_win_video, json_win_param, embed_referer)
            except Exception as e:
                logger.warning("Could not pre-fetch key during prepare: %s", e)
                key_hex = None
            token = _create_stream_session(m3u8_url, embed_referer, key_hex, {
                "type": "tv", "id": req.id, "episode_id": episode_id, "slug": req.slug,
                "episode_number": episode_num, "episode_title": resolved_title,
            })
            return token, episode_id, episode_num, resolved_title
        else:
            raise ValueError(f"Tipo di contenuto non supportato: {c_type}")

    try:
        token, ep_id, ep_num, ep_title = await asyncio.to_thread(_resolve)
    except Exception as e:
        logger.error("Failed to prepare stream: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Errore caricamento streaming: {str(e)}")

    return {
        "stream_token": token,
        "master_url": f"/api/stream/hls/{token}/master.m3u8",
        "content_type": c_type,
        "id": req.id,
        "episode_id": ep_id,
        "episode_number": ep_num,
        "episode_title": ep_title,
    }


@router.get("/hls/{token}/master.m3u8")
async def get_master_playlist(token: str):
    session = _get_stream_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Sessione di streaming non trovata o scaduta")

    if "master_content" in session:
        return Response(
            content=session["master_content"],
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    def _fetch():
        headers = {"user-agent": get_headers(), "referer": session["referer"]}
        url = session["m3u8_url"]
        r = _http_get(url, headers=headers, timeout=15)
        if r.status_code == 403:
            b1_url = url + ("&b=1" if "?" in url else "?b=1")
            r = _http_get(b1_url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.text, r.url

    try:
        text, final_url = await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.warning("Failed to fetch master M3U8: %s", e)
        raise HTTPException(status_code=502, detail="Errore nel recupero della playlist master")

    def _sub_media_uri(match):
        rel_uri = match.group(1)
        abs_uri = _make_abs_url(final_url, rel_uri)
        proxy_uri = f"/api/stream/hls/{token}/variant.m3u8?uri={quote_plus(abs_uri)}"
        return f'URI="{proxy_uri}"'

    text = re.sub(r'URI="([^"]+)"', _sub_media_uri, text)

    lines = []
    for line in text.splitlines():
        line_s = line.strip()
        if line_s and not line_s.startswith("#"):
            abs_uri = _make_abs_url(final_url, line_s)
            proxy_uri = f"/api/stream/hls/{token}/variant.m3u8?uri={quote_plus(abs_uri)}"
            lines.append(proxy_uri)
        else:
            lines.append(line)

    content = "\n".join(lines)
    session["master_content"] = content

    return Response(
        content=content,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.get("/hls/{token}/variant.m3u8")
async def get_variant_playlist(token: str, uri: str = Query(...)):
    session = _get_stream_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Sessione di streaming non trovata o scaduta")

    abs_playlist_url = unquote_plus(uri)

    variant_cache = session.setdefault("variant_cache", {})
    if abs_playlist_url in variant_cache:
        return Response(
            content=variant_cache[abs_playlist_url],
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    def _fetch():
        headers = {"user-agent": get_headers(), "referer": session["referer"]}
        r = _http_get(abs_playlist_url, headers=headers, timeout=15)
        if r.status_code == 403:
            b1_url = abs_playlist_url + ("&b=1" if "?" in abs_playlist_url else "?b=1")
            r = _http_get(b1_url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.text, r.url

    try:
        text, final_url = await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.warning("Failed to fetch variant M3U8 (%s): %s", abs_playlist_url, e)
        raise HTTPException(status_code=502, detail="Errore nel recupero della playlist variante")

    key_proxy_url = f"/api/stream/hls/{token}/key"
    text = re.sub(r'URI="[^"]+"', f'URI="{key_proxy_url}"', text)

    lines = []
    for line in text.splitlines():
        line_s = line.strip()
        if line_s and not line_s.startswith("#"):
            abs_seg = _make_abs_url(final_url, line_s)
            proxy_seg = f"/api/stream/hls/{token}/segment.ts?uri={quote_plus(abs_seg)}"
            lines.append(proxy_seg)
        else:
            lines.append(line)

    content = "\n".join(lines)
    variant_cache[abs_playlist_url] = content

    return Response(
        content=content,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.get("/hls/{token}/key")
async def get_stream_key(token: str):
    session = _get_stream_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Sessione di streaming non trovata o scaduta")

    key_hex = session.get("key_hex")
    if not key_hex:
        def _fetch_key():
            referer = session.get("referer", "")
            ref_parsed = urlparse(referer) if referer else None
            host = ref_parsed.netloc if (ref_parsed and ref_parsed.netloc) else "vixcloud.co"
            scheme = ref_parsed.scheme if (ref_parsed and ref_parsed.scheme) else "https"
            url = f"{scheme}://{host}/storage/enc.key"
            headers = {"user-agent": get_headers(), "referer": referer}
            r = _http_get(url, headers=headers, timeout=15)
            r.raise_for_status()
            return r.content

        try:
            key_bytes = await asyncio.to_thread(_fetch_key)
            session["key_hex"] = key_bytes.hex()
        except Exception as e:
            logger.error("Failed to fetch encryption key: %s", e)
            raise HTTPException(status_code=502, detail="Impossibile ottenere la chiave di decifrazione")
    else:
        try:
            key_bytes = bytes.fromhex(key_hex)
        except Exception:
            raise HTTPException(status_code=500, detail="Chiave di decifrazione non valida")

    return Response(
        content=key_bytes,
        media_type="application/octet-stream",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/hls/{token}/segment.ts")
async def get_stream_segment(token: str, uri: str = Query(...)):
    session = _get_stream_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Sessione di streaming non trovata o scaduta")

    abs_seg_url = unquote_plus(uri)
    if not (abs_seg_url.startswith("http://") or abs_seg_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="URL segmento non valido")

    now = time.time()
    with _SEGMENT_CACHE_LOCK:
        cached = _SEGMENT_CACHE.get(abs_seg_url)
        if cached and (now - cached[0] < _SEGMENT_TTL):
            return Response(
                content=cached[1],
                media_type="video/mp2t",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "public, max-age=86400",
                },
            )

    client = _get_http_session()
    headers = {"user-agent": get_headers(), "referer": session["referer"]}

    def _request():
        for attempt in range(3):
            try:
                r = client.get(abs_seg_url, headers=headers, timeout=(5, 20))
                if r.ok:
                    data = r.content
                    with _SEGMENT_CACHE_LOCK:
                        cur_time = time.time()
                        if len(_SEGMENT_CACHE) >= _MAX_SEGMENTS_CACHE:
                            expired = [k for k, v in _SEGMENT_CACHE.items() if (cur_time - v[0]) >= _SEGMENT_TTL]
                            for k in expired:
                                _SEGMENT_CACHE.pop(k, None)
                            if len(_SEGMENT_CACHE) >= _MAX_SEGMENTS_CACHE:
                                oldest_key = min(_SEGMENT_CACHE.keys(), key=lambda k: _SEGMENT_CACHE[k][0])
                                _SEGMENT_CACHE.pop(oldest_key, None)
                        _SEGMENT_CACHE[abs_seg_url] = (cur_time, data)
                    return data
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(0.2)
        raise RuntimeError(f"Impossibile scaricare segmento: HTTP {r.status_code if 'r' in locals() else 'error'}")

    try:
        content = await asyncio.to_thread(_request)
    except Exception as e:
        logger.warning("Segment fetch failed for %s: %s", abs_seg_url, e)
        raise HTTPException(status_code=502, detail="Errore nel recupero del segmento video")

    return Response(
        content=content,
        media_type="video/mp2t",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
        },
    )

