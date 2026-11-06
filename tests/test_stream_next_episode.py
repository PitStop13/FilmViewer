import pytest
from app.auth.permissions import Permission
from app.routers import stream as stream_router


@pytest.fixture
def mock_sc(monkeypatch):
    monkeypatch.setattr(stream_router, "_sc_domain", lambda: "example.test")
    monkeypatch.setattr(stream_router, "get_domain_version", lambda d: "v1")
    monkeypatch.setattr(stream_router, "_get_tv_token", lambda tv_id, d: "token123")


def test_next_episode_same_season(client, admin_credentials, mock_sc, monkeypatch):
    from tests.test_permissions import do_setup, _as

    do_setup(client, admin_credentials)
    client.cookies.clear()
    _, csrf = _as(client, Permission.VIEW_LIBRARY | Permission.REQUEST)

    s1_eps = [
        {"id": 101, "n": 1, "name": "Pilot", "still": "/api/image/still1.jpg", "duration": 45},
        {"id": 102, "n": 2, "name": "Cat's in the Bag...", "still": "/api/image/still2.jpg", "duration": 48},
        {"id": 103, "n": 3, "name": "...And the Bag's in the River", "still": "/api/image/still3.jpg", "duration": 48},
    ]

    def mock_info_season(tv_id, slug, domain, version, token, season):
        if season == 1:
            return s1_eps
        return []

    monkeypatch.setattr(stream_router, "_get_info_season", mock_info_season)
    monkeypatch.setattr(stream_router, "_get_info_tv", lambda tv_id, slug, v, d: 1)

    # From Ep 1 by episode_number
    res = client.get("/api/stream/next-episode?id=1&slug=test&season_number=1&episode_number=1")
    assert res.status_code == 200
    data = res.json()
    assert data["has_next"] is True
    assert data["next_episode"]["episode_id"] == "102"
    assert data["next_episode"]["episode_number"] == 2
    assert data["next_episode"]["season_number"] == 1
    assert data["next_episode"]["name"] == "Cat's in the Bag..."

    # From Ep 1 by episode_id
    res = client.get("/api/stream/next-episode?id=1&slug=test&season_number=1&episode_id=101")
    assert res.status_code == 200
    data = res.json()
    assert data["has_next"] is True
    assert data["next_episode"]["episode_id"] == "102"
    assert data["next_episode"]["episode_number"] == 2


def test_next_episode_across_seasons(client, admin_credentials, mock_sc, monkeypatch):
    from tests.test_permissions import do_setup, _as

    do_setup(client, admin_credentials)
    client.cookies.clear()
    _, csrf = _as(client, Permission.VIEW_LIBRARY | Permission.REQUEST)

    s1_eps = [
        {"id": 101, "n": 1, "name": "S1E1"},
        {"id": 102, "n": 2, "name": "S1 Finale"},
    ]
    s2_eps = [
        {"id": 201, "n": 1, "name": "S2 Premiere", "still": "/api/image/s2e1.jpg", "duration": 50},
    ]

    def mock_info_season(tv_id, slug, domain, version, token, season):
        if season == 1:
            return s1_eps
        elif season == 2:
            return s2_eps
        return []

    monkeypatch.setattr(stream_router, "_get_info_season", mock_info_season)
    monkeypatch.setattr(stream_router, "_get_info_tv", lambda tv_id, slug, v, d: 2)

    # From S1E2 (last episode of S1) -> Should return S2E1
    res = client.get("/api/stream/next-episode?id=1&slug=test&season_number=1&episode_number=2&episode_id=102")
    assert res.status_code == 200
    data = res.json()
    assert data["has_next"] is True
    assert data["next_episode"]["episode_id"] == "201"
    assert data["next_episode"]["episode_number"] == 1
    assert data["next_episode"]["season_number"] == 2
    assert data["next_episode"]["name"] == "S2 Premiere"


def test_next_episode_at_series_end(client, admin_credentials, mock_sc, monkeypatch):
    from tests.test_permissions import do_setup, _as

    do_setup(client, admin_credentials)
    client.cookies.clear()
    _, csrf = _as(client, Permission.VIEW_LIBRARY | Permission.REQUEST)

    s1_eps = [
        {"id": 101, "n": 1, "name": "Only Episode"},
    ]

    monkeypatch.setattr(stream_router, "_get_info_season", lambda *a, **k: s1_eps)
    monkeypatch.setattr(stream_router, "_get_info_tv", lambda *a, **k: 1)

    res = client.get("/api/stream/next-episode?id=1&slug=test&season_number=1&episode_number=1&episode_id=101")
    assert res.status_code == 200
    data = res.json()
    assert data["has_next"] is False
    assert data["next_episode"] is None
