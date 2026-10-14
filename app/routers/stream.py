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


def _get_http_session() -> requests.Session:
    global _http_session
    with _http_session_lock:
        if _http_session is None:
            _http_session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=1)
            _http_session.mount("https://", adapter)
            _http_session.mount("http://", adapter)
        return _http_session


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


@router.get("/watch-info")
async def get_watch_info(
    content_type: str = Query(..., alias="content_type"),
    id: str = Query(...),
    slug: str = Query(""),
    episode_id: Optional[str] = Query(None),
    episode_number: Optional[str] = Query(None),
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
async def prepare_stream(req: StreamPrepareRequest):
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
            return token
        elif c_type in ("tv", "series"):
            if not req.episode_id:
                raise ValueError("ID episodio obbligatorio per le serie TV")
            sc_token = _get_tv_token(int(req.id), domain)
            embed_content, embed_referer = _get_tv_iframe(int(req.id), int(req.episode_id), domain, sc_token)
            json_win_video, json_win_param = _parse_content(embed_content, embed_referer)
            m3u8_url = _get_m3u8_url(json_win_video, json_win_param)
            try:
                key_hex = _get_m3u8_key(json_win_video, json_win_param, embed_referer)
            except Exception as e:
                logger.warning("Could not pre-fetch key during prepare: %s", e)
                key_hex = None
            token = _create_stream_session(m3u8_url, embed_referer, key_hex, {
                "type": "tv", "id": req.id, "episode_id": req.episode_id, "slug": req.slug
            })
            return token
        else:
            raise ValueError(f"Tipo di contenuto non supportato: {c_type}")

    try:
        token = await asyncio.to_thread(_resolve)
    except Exception as e:
        logger.error("Failed to prepare stream: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Errore caricamento streaming: {str(e)}")

    return {
        "stream_token": token,
        "master_url": f"/api/stream/hls/{token}/master.m3u8",
        "content_type": c_type,
        "id": req.id,
    }


@router.get("/hls/{token}/master.m3u8")
async def get_master_playlist(token: str):
    session = _get_stream_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Sessione di streaming non trovata o scaduta")

    def _fetch():
        headers = {"user-agent": get_headers(), "referer": session["referer"]}
        url = session["m3u8_url"]
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 403:
            b1_url = url + ("&b=1" if "?" in url else "?b=1")
            r = requests.get(b1_url, headers=headers, timeout=15)
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

    return Response(
        content="\n".join(lines),
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

    def _fetch():
        headers = {"user-agent": get_headers(), "referer": session["referer"]}
        r = requests.get(abs_playlist_url, headers=headers, timeout=15)
        if r.status_code == 403:
            b1_url = abs_playlist_url + ("&b=1" if "?" in abs_playlist_url else "?b=1")
            r = requests.get(b1_url, headers=headers, timeout=15)
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

    return Response(
        content="\n".join(lines),
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
            headers = {"user-agent": get_headers(), "referer": session["referer"]}
            r = requests.get("https://vixcloud.co/storage/enc.key", headers=headers, timeout=15)
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

    client = _get_http_session()
    headers = {"user-agent": get_headers(), "referer": session["referer"]}

    def _request():
        for attempt in range(3):
            try:
                r = client.get(abs_seg_url, headers=headers, stream=True, timeout=(5, 20))
                if r.ok:
                    return r
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(0.4)
        raise RuntimeError(f"Impossibile scaricare segmento: HTTP {r.status_code if 'r' in locals() else 'error'}")

    try:
        r = await asyncio.to_thread(_request)
    except Exception as e:
        logger.warning("Segment fetch failed for %s: %s", abs_seg_url, e)
        raise HTTPException(status_code=502, detail="Errore nel recupero del segmento video")

    return StreamingResponse(
        r.iter_content(chunk_size=65536),
        media_type="video/mp2t",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
        },
    )

