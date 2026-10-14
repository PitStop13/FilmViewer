import pytest
from app.routers import stream
from tests.conftest import enable_open_mode

MASTER_M3U8 = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Italiano",DEFAULT=YES,URI="audio/ita.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
1080/playlist.m3u8
"""

VARIANT_M3U8 = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:4
#EXT-X-KEY:METHOD=AES-128,URI="https://vixcloud.co/storage/enc.key",IV=0x1234567890abcdef1234567890abcdef
#EXTINF:4.000,
seg_001.ts
#EXTINF:4.000,
seg_002.ts
"""


def test_stream_session_creation_and_retrieval():
    token = stream._create_stream_session(
        m3u8_url="https://vixcloud.co/playlist/123?token=abc",
        referer="https://vixcloud.co/embed/123",
        key_hex="00112233445566778899aabbccddeeff",
        meta={"type": "movie", "id": "123"},
    )
    assert token
    session = stream._get_stream_session(token)
    assert session is not None
    assert session["m3u8_url"] == "https://vixcloud.co/playlist/123?token=abc"
    assert session["key_hex"] == "00112233445566778899aabbccddeeff"


def test_stream_key_endpoint(client):
    enable_open_mode()
    token = stream._create_stream_session(
        m3u8_url="https://vixcloud.co/playlist/123",
        referer="https://vixcloud.co/embed/123",
        key_hex="00112233445566778899aabbccddeeff",
        meta={"type": "movie"},
    )
    res = client.get(f"/api/stream/hls/{token}/key")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/octet-stream")
    assert res.content == bytes.fromhex("00112233445566778899aabbccddeeff")


def test_master_playlist_rewriting(client, monkeypatch):
    enable_open_mode()
    token = stream._create_stream_session(
        m3u8_url="https://vixcloud.co/playlist/123?token=abc&expires=999",
        referer="https://vixcloud.co/embed/123",
        key_hex="00112233445566778899aabbccddeeff",
        meta={"type": "movie"},
    )

    class FakeResponse:
        text = MASTER_M3U8
        status_code = 200
        url = "https://vixcloud.co/playlist/123?token=abc&expires=999"
        def raise_for_status(self): pass

    monkeypatch.setattr(stream.requests, "get", lambda *a, **kw: FakeResponse())

    res = client.get(f"/api/stream/hls/{token}/master.m3u8")
    assert res.status_code == 200
    body = res.text
    # Variant and media lines should be rewritten to local proxy URLs
    assert f"/api/stream/hls/{token}/variant.m3u8?uri=" in body
    assert "https%3A%2F%2Fvixcloud.co%2Fplaylist%2F1080%2Fplaylist.m3u8" in body
    assert "https%3A%2F%2Fvixcloud.co%2Fplaylist%2Faudio%2Fita.m3u8" in body


def test_variant_playlist_rewriting(client, monkeypatch):
    enable_open_mode()
    token = stream._create_stream_session(
        m3u8_url="https://vixcloud.co/playlist/123",
        referer="https://vixcloud.co/embed/123",
        key_hex="00112233445566778899aabbccddeeff",
        meta={"type": "movie"},
    )

    class FakeResponse:
        text = VARIANT_M3U8
        status_code = 200
        url = "https://vixcloud.co/playlist/1080/playlist.m3u8?token=abc"
        def raise_for_status(self): pass

    monkeypatch.setattr(stream.requests, "get", lambda *a, **kw: FakeResponse())

    res = client.get(f"/api/stream/hls/{token}/variant.m3u8?uri=https://vixcloud.co/playlist/1080/playlist.m3u8")
    assert res.status_code == 200
    body = res.text
    # Key URI rewritten to local key endpoint, IV preserved
    assert f'URI="/api/stream/hls/{token}/key"' in body
    assert "IV=0x1234567890abcdef1234567890abcdef" in body
    # Segments rewritten to segment proxy
    assert f"/api/stream/hls/{token}/segment.ts?uri=" in body
    assert "seg_001.ts" in body
