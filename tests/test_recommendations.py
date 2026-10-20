import pytest

from app import continue_watching as cw_service
from app.core import home, page
from tests.conftest import enable_open_mode


def test_watch_history_records_completion_and_candidates():
    # Save a finished movie (98% watched)
    cw_service.save_progress(
        content_type="movie",
        content_id="999",
        title="Interstellar",
        slug="interstellar",
        position_seconds=7050,
        duration_seconds=7200,
        user_id=42,
    )

    # It was auto-deleted from continue_watching because it's finished...
    assert cw_service.get_item("movie", "999", user_id=42) is None

    # ...BUT watch_history remembers it and prioritizes it for recommendations!
    candidates = cw_service.get_recommendation_candidates(user_id=42, content_type="movie")
    assert len(candidates) >= 1
    top = candidates[0]
    assert top["content_id"] == "999"
    assert top["title"] == "Interstellar"
    assert top["completed"] is True


def test_watch_history_prioritizes_binged_series():
    # Save episode 1 (partially watched)
    cw_service.save_progress(
        content_type="tv",
        content_id="888",
        title="Dark",
        slug="dark",
        position_seconds=1200,
        duration_seconds=3600,
        episode_number=1,
        user_id=10,
    )
    # Save episode 3 (completed)
    cw_service.save_progress(
        content_type="tv",
        content_id="888",
        title="Dark",
        slug="dark",
        position_seconds=3550,
        duration_seconds=3600,
        episode_number=3,
        user_id=10,
    )

    candidates = cw_service.get_recommendation_candidates(user_id=10, content_type="tv")
    assert len(candidates) >= 1
    assert candidates[0]["title"] == "Dark"
    assert candidates[0]["completed"] is True


def test_home_generates_personalized_shelf_from_watch_history(monkeypatch):
    # Setup watched movie in history
    cw_service.save_progress(
        content_type="movie",
        content_id="777",
        title="Il Gladiatore",
        slug="il-gladiatore",
        position_seconds=7100,
        duration_seconds=7200,
        user_id=5,
    )

    # Mock page props for Gladiator title page to return related slider
    def fake_fetch_page_props(url, params=None, timeout=10):
        if "777-il-gladiatore" in url:
            return {
                "sliders": [
                    {
                        "name": "related",
                        "titles": [
                            {"id": 101, "name": "Troy", "slug": "troy", "type": "movie", "images": []},
                            {"id": 102, "name": "300", "slug": "300", "type": "movie", "images": []},
                            {"id": 103, "name": "Spartacus", "slug": "spartacus", "type": "movie", "images": []},
                            {"id": 104, "name": "Alexander", "slug": "alexander", "type": "movie", "images": []},
                        ],
                    }
                ]
            }
        # Fallback for archive queries
        return {
            "titles": [
                {"id": 201, "name": "Archive Film 1", "slug": "af-1", "type": "movie", "images": []},
                {"id": 202, "name": "Archive Film 2", "slug": "af-2", "type": "movie", "images": []},
            ]
        }

    monkeypatch.setattr(page, "fetch_page_props", fake_fetch_page_props)

    shelves = home.shelves("streamingcommunity", "source.test", category="movie", user_id=5)

    # There should be an authentic core shelf, dynamic shelves, and our personalized recommendation shelf
    rec_shelf = next((s for s in shelves if s["key"] == "rec_movie_777"), None)
    assert rec_shelf is not None
    assert rec_shelf["title"] == "Perché hai guardato Il Gladiatore"
    assert rec_shelf["category"] == "movie"
    assert any(i["name"] == "Troy" for i in rec_shelf["items"])


def test_home_refresh_parameter_bypasses_cache(monkeypatch):
    calls = []

    def fake_fetch_page_props(url, params=None, timeout=10):
        calls.append(url)
        return {"titles": [{"id": 1, "name": "Film", "slug": "film", "type": "movie", "images": []}]}

    monkeypatch.setattr(page, "fetch_page_props", fake_fetch_page_props)

    # First fetch: populates cache
    home.shelves("streamingcommunity", "source.test", category="movie", user_id=1, refresh=False)
    count_after_first = len(calls)
    assert count_after_first > 0

    # Second fetch without refresh: hit cache
    home.shelves("streamingcommunity", "source.test", category="movie", user_id=1, refresh=False)
    assert len(calls) == count_after_first

    # Third fetch with refresh=True: bypasses cache and re-queries
    home.shelves("streamingcommunity", "source.test", category="movie", user_id=1, refresh=True)
    assert len(calls) > count_after_first
