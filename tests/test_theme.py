"""Tests for user theme preferences, preset palettes, and API endpoints."""

import pytest
from app import db
from app.auth import models
from tests.conftest import make_user, session_for


def test_user_theme_default_and_model():
    user = models.create_local_user(
        username="theme_user1",
        password="password123",
        is_admin=False,
    )
    assert user.theme == "default"
    public = user.to_public()
    assert public["theme"] == "default"

    # Update theme via model helper
    updated_theme = models.update_user_theme(user.id, "rose")
    assert updated_theme == "rose"

    refetched = models.get_user(user.id)
    assert refetched.theme == "rose"
    assert refetched.to_public()["theme"] == "rose"


def test_update_user_theme_invalid_fallback():
    user = models.create_local_user(
        username="theme_user_invalid",
        password="password123",
        is_admin=False,
    )
    res = models.update_user_theme(user.id, "invalid_funky_color")
    assert res == "default"
    assert models.get_user(user.id).theme == "default"


def test_theme_api_endpoint_flow(client):
    # Setup user and session
    user = make_user("theme_tester", "jf-theme-tester", 0)
    csrf = session_for(client, user.id)

    # Initial /api/auth/me has default theme
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"]["theme"] == "default"

    # Set theme to emerald
    res = client.put(
        "/api/auth/theme",
        json={"theme": "emerald"},
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True, "theme": "emerald"}

    # /api/auth/me reflects the new theme
    me_res2 = client.get("/api/auth/me")
    assert me_res2.status_code == 200
    assert me_res2.json()["user"]["theme"] == "emerald"

    # Rejection of unknown theme
    fail_res = client.put(
        "/api/auth/theme",
        json={"theme": "super_neon_unknown"},
        headers={"X-CSRF-Token": csrf},
    )
    assert fail_res.status_code == 400


def test_theme_per_user_isolation(client):
    """Confirm different users retain independent theme selections."""
    user_a = make_user("alice_theme", "jf-alice-theme", 0)
    user_b = make_user("bob_theme", "jf-bob-theme", 0)

    csrf_a = session_for(client, user_a.id)

    # Alice selects rose
    res_a = client.put(
        "/api/auth/theme",
        json={"theme": "rose"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert res_a.status_code == 200

    # Switch to Bob
    csrf_b = session_for(client, user_b.id)

    # Bob selects amber
    res_b = client.put(
        "/api/auth/theme",
        json={"theme": "amber"},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert res_b.status_code == 200

    # Check database rows directly
    assert models.get_user(user_a.id).theme == "rose"
    assert models.get_user(user_b.id).theme == "amber"
