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
