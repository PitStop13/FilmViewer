"""Stream resolution: the seam where a fallback provider would plug in.

A second road through vixsrc.to was built and then removed — that site is now a
client-rendered app whose HTML carries no playlist at all. What survives is the
shape a future provider would use, and these tests pin the parts that are easy
to get wrong when one is added.

The load-bearing behaviour: with nothing to fall back to, the *original*
exception must survive. A user told "no alternative source" when what actually
happened was a Cloudflare block has been sent to debug the wrong thing.
"""

import pytest

from app.core import _shared


MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
360/playlist.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
1080/playlist.m3u8
"""

MEDIA = """#EXTM3U
#EXT-X-KEY:METHOD=AES-128,URI="https://vixcloud.co/storage/enc.key",IV=0x00
#EXTINF:6.0,
seg-1.ts
"""

MEDIA_UNENCRYPTED = """#EXTM3U
#EXTINF:6.0,
seg-1.ts
"""

MEDIA_HOSTILE_KEY = """#EXTM3U
#EXT-X-KEY:METHOD=AES-128,URI="http://evil.example/key.bin",IV=0x00
#EXTINF:6.0,
seg-1.ts
"""


class _Response:
    def __init__(self, text="", status_code=200, content=b"\x11" * 16):
        self.text = text
        self.status_code = status_code
        self.content = content
        self.ok = status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


# ── The AES key, read rather than assumed ─────────────────────────────────────

@pytest.fixture
def playlists(monkeypatch):
    """Serve a master, its best variant, and the key. Records what was fetched."""
    fetched = []

    def fake_get(url, *args, **kwargs):
        fetched.append(url)
        if url.endswith("enc.key"):
            return _Response(content=b"\x11" * 16)
        if "1080/playlist.m3u8" in url:
            return _Response(MEDIA)
        return _Response(MASTER)

    monkeypatch.setattr(_shared.requests, "get", fake_get)
    from app.core import m3u8

    monkeypatch.setattr(m3u8.requests, "get", fake_get)
    return fetched


def test_the_key_is_taken_from_the_media_playlist(playlists):
    """The master usually carries no EXT-X-KEY; the variant does."""
    key = _shared.fetch_key_from_playlist("https://vixcloud.co/playlist/1", "https://vixsrc.to/")

    assert key == "11" * 16
    assert any("1080/playlist.m3u8" in url for url in playlists)


def test_the_best_variant_is_the_one_followed(playlists):
    _shared.fetch_key_from_playlist("https://vixcloud.co/playlist/1", "https://vixsrc.to/")
    assert not any("360/playlist.m3u8" in url for url in playlists)


def test_an_unencrypted_playlist_has_no_key(monkeypatch):
    def fake_get(url, *args, **kwargs):
        return _Response(MEDIA_UNENCRYPTED if "1080" in url else MASTER)

    monkeypatch.setattr(_shared.requests, "get", fake_get)
    from app.core import m3u8

    monkeypatch.setattr(m3u8.requests, "get", fake_get)

    assert _shared.fetch_key_from_playlist("https://vixcloud.co/playlist/1", "r") is None


def test_a_key_on_someone_elses_host_is_refused(monkeypatch):
    """The playlist is published by the stream page; it does not get to pick hosts."""
    reached = []

    def fake_get(url, *args, **kwargs):
        reached.append(url)
        return _Response(MEDIA_HOSTILE_KEY if "1080" in url else MASTER)

    monkeypatch.setattr(_shared.requests, "get", fake_get)
    from app.core import m3u8

    monkeypatch.setattr(m3u8.requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="host non consentito"):
        _shared.fetch_key_from_playlist("https://vixcloud.co/playlist/1", "r")

    assert not any("evil.example" in url for url in reached)


# ── resolve_stream ────────────────────────────────────────────────────────────

def _source():
    return _shared.StreamSource("https://x/p.m3u8", None, "r", "vixcloud")


def test_a_working_primary_is_never_second_guessed(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the fallback ran despite a working primary")

    monkeypatch.setattr(_shared, "_FALLBACK_PROVIDERS", (boom,))

    assert _shared.resolve_stream(_source, tmdb_id=1396).provider == "vixcloud"


def test_a_registered_provider_runs_when_the_primary_fails(monkeypatch):
    monkeypatch.setattr(
        _shared, "_FALLBACK_PROVIDERS",
        (lambda *a: _shared.StreamSource("https://v/p.m3u8", None, "r", "other"),),
    )

    def failing():
        raise RuntimeError("403 Cloudflare")

    assert _shared.resolve_stream(failing, tmdb_id=1396).provider == "other"


def test_with_no_provider_registered_the_primary_error_survives():
    """The shipped state: nothing is registered, so this is what users see."""
    assert _shared._FALLBACK_PROVIDERS == ()

    def failing():
        raise RuntimeError("403 Cloudflare")

    with pytest.raises(RuntimeError, match="403 Cloudflare"):
        _shared.resolve_stream(failing, tmdb_id=1396)


def test_without_a_tmdb_id_the_original_error_survives(monkeypatch):
    """Reporting a missing id sends the user to debug something that is not wrong."""
    monkeypatch.setattr(
        _shared, "_FALLBACK_PROVIDERS",
        (lambda *a: _shared.StreamSource("https://v/p.m3u8", None, "r", "other"),),
    )

    def failing():
        raise RuntimeError("403 Cloudflare")

    with pytest.raises(RuntimeError, match="403 Cloudflare"):
        _shared.resolve_stream(failing, tmdb_id=None)


def test_both_failures_are_reported_together(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider 404")

    monkeypatch.setattr(_shared, "_FALLBACK_PROVIDERS", (boom,))

    def failing():
        raise RuntimeError("403 Cloudflare")

    with pytest.raises(_shared.StreamResolutionError) as excinfo:
        _shared.resolve_stream(failing, tmdb_id=1396)

    message = str(excinfo.value)
    assert "403 Cloudflare" in message
    assert "provider 404" in message


# ── Wiring ────────────────────────────────────────────────────────────────────

def test_the_anime_path_has_no_fallback_to_offer():
    """An anime here has no TMDB id and its embed lives elsewhere.

    Pinned as a signature check: quietly adding the parameter for symmetry would
    give AnimeUnity a fallback that cannot work.
    """
    import inspect

    from app.jobs import job_manager

    assert "tmdb_id" not in inspect.signature(job_manager.submit_anime_episode).parameters
    assert "tmdb_id" in inspect.signature(job_manager.submit_film).parameters
    assert "tmdb_id" in inspect.signature(job_manager.submit_episode).parameters


def test_a_film_uses_a_registered_provider_when_the_embed_is_blocked(monkeypatch, tmp_path):
    from app.core import film

    monkeypatch.setattr(
        film, "_get_iframe",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("403 Cloudflare")),
    )
    # Patched on _shared, not on film: resolve_stream lives there and reads the
    # provider tuple as its own module global.
    monkeypatch.setattr(
        _shared, "_FALLBACK_PROVIDERS",
        (lambda *a: _shared.StreamSource("https://v/p.m3u8", "aa" * 16, "r", "other"),),
    )
    monkeypatch.setattr(film, "_collect_audio_tracks", lambda *a, **k: [])
    monkeypatch.setattr(film, "_collect_subtitle_tracks", lambda *a, **k: [])

    used = {}

    def fake_download(**kwargs):
        used.update(kwargs)
        return kwargs["output_filename"]

    monkeypatch.setattr(film, "download_m3u8", fake_download)

    film.download_film(1, "Test", "example.test", output_dir=str(tmp_path), tmdb_id=1396)

    assert used["m3u8_index"] == "https://v/p.m3u8"
    assert used["key"] == "aa" * 16


def test_a_film_without_a_tmdb_id_still_reports_the_real_error(monkeypatch, tmp_path):
    from app.core import film

    monkeypatch.setattr(
        film, "_get_iframe",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("403 Cloudflare")),
    )

    with pytest.raises(RuntimeError, match="403 Cloudflare"):
        film.download_film(1, "Test", "example.test", output_dir=str(tmp_path))


# ── Dynamic Embed Host Resolution ─────────────────────────────────────────────

def test_parse_content_extracts_dynamic_host_and_playlist_url():
    snippet = """
    window.video = { id: '999' };
    window.masterPlaylist = {
        params: { 'token': 'abc', 'expires': '123' },
        url: 'https://vixcloud.cc/playlist/999'
    };
    """
    video, param = _shared._parse_content(snippet, "https://vixcloud.cc/embed/999?scz=1")
    assert video["id"] == "999"
    assert video["host"] == "vixcloud.cc"
    assert video["base_url"] == "https://vixcloud.cc"
    assert video["playlist_url"] == "https://vixcloud.cc/playlist/999"
    assert param["token"] == "abc"
    assert param["expires"] == "123"

    m3u8_url = _shared._get_m3u8_url(video, param)
    assert m3u8_url.startswith("https://vixcloud.cc/playlist/999?")
    assert "token=abc" in m3u8_url


def test_get_m3u8_key_uses_dynamic_referer_host(monkeypatch):
    fetched = []

    def fake_get(url, *args, **kwargs):
        fetched.append(url)
        return _Response(content=b"\x42" * 16)

    monkeypatch.setattr(_shared.requests, "get", fake_get)
    key = _shared._get_m3u8_key(
        {"id": "999", "base_url": "https://vixcloud.cc"},
        {"token": "abc"},
        referer="https://vixcloud.cc/embed/999",
    )
    assert key == "42" * 16
    assert fetched == ["https://vixcloud.cc/storage/enc.key"]


def test_key_hosts_allows_vixcloud_rotations():
    assert _shared._is_allowed_key_host("vixcloud.cc", "https://vixcloud.cc/playlist/1")
    assert _shared._is_allowed_key_host("vixcloud.co", "https://vixcloud.co/playlist/1")
    assert _shared._is_allowed_key_host("vixcloud.to", "https://vixcloud.to/playlist/1")
    assert not _shared._is_allowed_key_host("attacker.example", "https://vixcloud.cc/playlist/1")


def test_prepare_tv_stream_auto_resolves_episode(monkeypatch, client):
    from tests.conftest import enable_open_mode
    enable_open_mode()

    # Mock domain, token, watch page, iframe, parse content, m3u8 and key
    from app.routers import stream as stream_router
    monkeypatch.setattr(stream_router, "_sc_domain", lambda: "mock.example")
    monkeypatch.setattr(stream_router, "_get_tv_token", lambda tv_id, domain: "mock_token")

    class FakeWatchResponse:
        ok = True
        status_code = 200
        text = '''
        <div id="app" data-page='{"props":{"episode":{"id":777,"number":1,"name":"Pilot Episode"}}}'></div>
        '''

    monkeypatch.setattr(stream_router.requests, "get", lambda *args, **kwargs: FakeWatchResponse())
    monkeypatch.setattr(stream_router, "_get_tv_iframe", lambda tv_id, ep_id, domain, token: ("mock_content", "https://vixcloud.cc/embed/777"))
    monkeypatch.setattr(stream_router, "_parse_content", lambda content, referer: ({"id": "777"}, {"token": "xyz", "expires": "999"}))
    monkeypatch.setattr(stream_router, "_get_m3u8_url", lambda v, p: "https://vixcloud.cc/playlist/777.m3u8")
    monkeypatch.setattr(stream_router, "_get_m3u8_key", lambda v, p, ref: "abcdef123456")

    res = client.post("/api/stream/prepare", json={
        "content_type": "tv",
        "id": "123",
        "slug": "test-series"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["content_type"] == "tv"
    assert data["id"] == "123"
    assert data["episode_id"] == "777"
    assert data["episode_number"] == "1"
    assert data["episode_title"] == "Pilot Episode"
    assert data["master_url"].startswith("/api/stream/hls/")


