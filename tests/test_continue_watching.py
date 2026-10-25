import pytest
from app import continue_watching as cw_service
from tests.conftest import enable_open_mode


def test_empty_continue_watching_list(client):
    enable_open_mode()
    res = client.get("/api/continue-watching")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_save_and_retrieve_movie_progress(client):
    enable_open_mode()

    # Save progress: 30 minutes into a 120-minute movie (25%)
    payload = {
        "content_type": "movie",
        "content_id": "100",
        "slug": "film-test",
        "title": "Film di Prova",
        "poster": "https://example.com/poster.jpg",
        "position_seconds": 1800,
        "duration_seconds": 7200,
    }
    res = client.post("/api/continue-watching/progress", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "saved"

    # Retrieve list
    res = client.get("/api/continue-watching")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["id"] == "movie:100"
    assert item["content_type"] == "movie"
    assert item["content_id"] == "100"
    assert item["title"] == "Film di Prova"
    assert item["percentage"] == 25
    assert item["remaining_seconds"] == 5400


def test_save_and_retrieve_tv_progress(client):
    enable_open_mode()

    payload = {
        "content_type": "tv",
        "content_id": "200",
        "slug": "serie-test",
        "title": "Serie di Prova",
        "poster": "https://example.com/series.jpg",
        "episode_id": "555",
        "episode_number": 3,
        "season_number": 1,
        "episode_title": "La Verità",
        "position_seconds": 1200,
        "duration_seconds": 3600,
    }
    res = client.post("/api/continue-watching/progress", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "saved"

    # Retrieve item
    item = cw_service.get_item("tv", "200")
    assert item is not None
    assert item["id"] == "tv:200"
    assert item["episode_number"] == 3
    assert item["season_number"] == 1
    assert item["episode_title"] == "La Verità"
    assert item["percentage"] == 33


def test_auto_delete_when_movie_finished(client):
    enable_open_mode()

    # Save initial progress
    payload = {
        "content_type": "movie",
        "content_id": "300",
        "title": "Film Quasi Finito",
        "position_seconds": 3600,
        "duration_seconds": 7200,
    }
    client.post("/api/continue-watching/progress", json=payload)
    assert len(cw_service.get_continue_watching_list()) >= 1

    # Now report finished (> 95% watched)
    payload["position_seconds"] = 7000  # 7000 / 7200 = ~97.2%
    res = client.post("/api/continue-watching/progress", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "finished"
    assert res.json()["deleted"] is True

    # Item should be gone from continue watching
    assert cw_service.get_item("movie", "300") is None


def test_manual_delete_continue_watching(client):
    enable_open_mode()

    # Save progress
    payload = {
        "content_type": "movie",
        "content_id": "400",
        "title": "Film Da Rimuovere",
        "position_seconds": 1000,
        "duration_seconds": 5000,
    }
    client.post("/api/continue-watching/progress", json=payload)
    assert cw_service.get_item("movie", "400") is not None

    # Delete via POST /api/continue-watching/delete
    res = client.post("/api/continue-watching/delete", json={"content_type": "movie", "content_id": "400"})
    assert res.status_code == 200
    assert res.json()["deleted"] is True

    # Assert removed
    assert cw_service.get_item("movie", "400") is None


def test_save_progress_without_duration_seconds(client):
    enable_open_mode()

    # Payload matching the exact frontend structure without duration_seconds
    payload = {
        "content_type": "movie",
        "content_id": "500",
        "slug": "film-no-duration",
        "title": "Film Senza Durata",
        "position_seconds": 120,
    }
    res = client.post("/api/continue-watching/progress", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "saved"

    item = cw_service.get_item("movie", "500")
    assert item is not None
    assert item["title"] == "Film Senza Durata"
    assert item["position_seconds"] == 120.0


def test_continue_watching_cross_user_fallback():
    # Save an item under user 0 (guest / open mode)
    cw_service.save_progress(
        content_type="movie",
        content_id="600",
        title="Film Ospite",
        position_seconds=500,
        duration_seconds=2000,
        user_id=0,
    )

    # User 1 (authenticated admin) should see the guest item
    user1_list = cw_service.get_continue_watching_list(user_id=1)
    assert any(i["content_id"] == "600" for i in user1_list)
    assert cw_service.get_item("movie", "600", user_id=1) is not None

    # Save an item under user 1
    cw_service.save_progress(
        content_type="tv",
        content_id="700",
        title="Serie Admin",
        position_seconds=300,
        duration_seconds=1800,
        episode_id="999",
        episode_number=5,
        season_number=2,
        episode_title="Finale",
        user_id=1,
    )

    # Guest user (user_id=0) should see both items
    guest_list = cw_service.get_continue_watching_list(user_id=0)
    assert any(i["content_id"] == "600" for i in guest_list)
    assert any(i["content_id"] == "700" for i in guest_list)
    assert cw_service.get_item("tv", "700", user_id=0) is not None

