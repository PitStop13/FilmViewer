import pytest
from app import favorites as fav_service
from tests.conftest import enable_open_mode


def test_empty_favorites_list(client):
    enable_open_mode()
    res = client.get("/api/favorites")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_add_and_retrieve_movie_favorite(client):
    enable_open_mode()

    payload = {
        "media_type": "movie",
        "content_id": "1001",
        "title": "Interstellar",
        "slug": "interstellar",
        "poster": "https://example.com/interstellar.jpg",
        "year": "2014",
        "score": "8.7",
        "plot": "Un viaggio attraverso un cunicolo spaziale...",
    }
    res = client.post("/api/favorites", json=payload)
    assert res.status_code == 200
    assert res.json()["favorited"] is True

    # Check status
    res = client.get("/api/favorites/status", params={"media_type": "movie", "content_id": "1001"})
    assert res.status_code == 200
    assert res.json()["favorited"] is True

    # Retrieve list
    res = client.get("/api/favorites")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Interstellar"
    assert items[0]["media_type"] == "movie"
    assert items[0]["content_id"] == "1001"
    assert items[0]["year"] == "2014"


def test_add_tv_favorite_and_filtering(client):
    enable_open_mode()

    # Add TV show
    payload = {
        "media_type": "tv",
        "content_id": "2002",
        "title": "Breaking Bad",
        "slug": "breaking-bad",
        "poster": "https://example.com/breaking-bad.jpg",
        "year": "2008",
        "score": "9.5",
    }
    res = client.post("/api/favorites", json=payload)
    assert res.status_code == 200

    # Filter by TV
    res_tv = client.get("/api/favorites", params={"type": "tv"})
    assert res_tv.status_code == 200
    tv_items = res_tv.json()["items"]
    assert any(i["content_id"] == "2002" for i in tv_items)
    assert all(i["media_type"] == "tv" for i in tv_items)

    # Filter by Movie
    res_movie = client.get("/api/favorites", params={"type": "movie"})
    assert res_movie.status_code == 200
    movie_items = res_movie.json()["items"]
    assert not any(i["content_id"] == "2002" for i in movie_items)


def test_remove_favorite(client):
    enable_open_mode()

    # Add favorite
    payload = {
        "media_type": "movie",
        "content_id": "3003",
        "title": "Inception",
    }
    client.post("/api/favorites", json=payload)
    assert fav_service.is_favorite("movie", "3003") is True

    # Delete favorite
    res = client.delete("/api/favorites/movie/3003")
    assert res.status_code == 200
    assert res.json()["favorited"] is False

    # Check status
    assert fav_service.is_favorite("movie", "3003") is False


def test_favorites_cross_user_fallback():
    # Save favorite as guest user (user_id=0)
    fav_service.add_favorite(
        media_type="movie",
        content_id="4004",
        title="Pulp Fiction",
        user_id=0,
    )

    # User 1 should see the guest favorite
    u1_favs = fav_service.get_favorites_list(user_id=1)
    assert any(f["content_id"] == "4004" for f in u1_favs)
    assert fav_service.is_favorite("movie", "4004", user_id=1) is True

    # User 1 adds a TV favorite
    fav_service.add_favorite(
        media_type="tv",
        content_id="5005",
        title="Stranger Things",
        user_id=1,
    )

    # Guest user (user_id=0) should see both
    guest_favs = fav_service.get_favorites_list(user_id=0)
    assert any(f["content_id"] == "4004" for f in guest_favs)
    assert any(f["content_id"] == "5005" for f in guest_favs)
