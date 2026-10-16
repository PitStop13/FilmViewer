"""Tests for local user management, authentication, parental control, and isolated continue watching."""

import pytest
from app.auth import models
from app.auth.deps import require
from app.auth.permissions import Permission
from app import continue_watching as cw_service


def test_password_hashing():
    pwd = "secret-password-123"
    hashed = models.hash_password(pwd)
    assert hashed.startswith("pbkdf2:sha256:100000$")
    assert models.verify_password(pwd, hashed) is True
    assert models.verify_password("wrong-password", hashed) is False
    assert models.verify_password("", hashed) is False
    assert models.verify_password(pwd, "") is False


def test_all_content_allowed_for_all():
    for age in (None, 0, 6, 12, 13, 14, 16, 18, "18+", "VM14", "T"):
        assert models.is_title_allowed_for_profile(age, "adult") is True


def test_first_run_setup_and_login_flow(client):
    # Switch auth to local
    models.set_setting(models.SETTING_AUTH_MODE, "local")

    # 1. Status shows setup_done = False initially
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json()["setup_done"] is False
    assert res.json()["users_count"] == 0

    # 2. Complete setup: create Admin account
    setup_res = client.post("/api/auth/setup", json={"username": "superadmin", "password": "masterpassword"})
    assert setup_res.status_code == 200
    data = setup_res.json()
    assert data["user"]["username"] == "superadmin"
    assert data["user"]["is_admin"] is True

    # Setup cannot be called a second time
    res_second = client.post("/api/auth/setup", json={"username": "hacker", "password": "masterpassword"})
    assert res_second.status_code == 400

    # 3. /api/auth/me returns superadmin
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"]["username"] == "superadmin"

    # 4. Logout
    logout_res = client.post("/api/auth/logout", headers={"X-CSRF-Token": data["csrf_token"]})
    assert logout_res.status_code == 200

    # 5. Login with wrong password fails
    fail_res = client.post("/api/auth/login", json={"username": "superadmin", "password": "wrong"})
    assert fail_res.status_code == 401

    # 6. Login with correct password succeeds
    login_res = client.post("/api/auth/login", json={"username": "superadmin", "password": "masterpassword"})
    assert login_res.status_code == 200
    assert login_res.json()["user"]["username"] == "superadmin"


def test_user_management_crud_and_download_permissions(client, stub_jobs):
    models.set_setting(models.SETTING_AUTH_MODE, "local")
    admin = models.create_local_user("admin", "adminpwd", is_admin=True)

    # Login as admin
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "adminpwd"})
    csrf = login_res.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    # 1. Create a regular user (not admin)
    res_create = client.post(
        "/api/users",
        json={
            "username": "utente_standard",
            "password": "standardpassword",
            "is_admin": False,
        },
        headers=headers,
    )
    assert res_create.status_code == 200
    std_user = res_create.json()
    assert std_user["username"] == "utente_standard"
    assert std_user["is_admin"] is False

    # 2. List all users
    list_res = client.get("/api/users")
    assert list_res.status_code == 200
    users = list_res.json()
    assert len(users) == 2
    assert any(u["username"] == "utente_standard" for u in users)

    # 3. Admin CAN download
    dl_admin = client.post("/api/download/film", json={"id": 1, "title": "Film Prova"}, headers=headers)
    assert dl_admin.status_code == 202

    # 4. Login as standard user
    client.post("/api/auth/logout", headers=headers)
    std_login = client.post("/api/auth/login", json={"username": "utente_standard", "password": "standardpassword"})
    assert std_login.status_code == 200
    std_csrf = std_login.json()["csrf_token"]
    std_headers = {"X-CSRF-Token": std_csrf}

    # 5. Standard user CANNOT download (Forbidden 403)
    dl_std = client.post("/api/download/film", json={"id": 2, "title": "Film Negato"}, headers=std_headers)
    assert dl_std.status_code == 403

    # Standard user CANNOT access user management
    assert client.get("/api/users").status_code == 403

    # 6. Re-login as admin to delete user
    client.post("/api/auth/logout", headers=std_headers)
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "adminpwd"})
    admin_csrf = login_res.json()["csrf_token"]
    admin_headers = {"X-CSRF-Token": admin_csrf}

    # Delete standard user
    del_res = client.delete(f"/api/users/{std_user['id']}", headers=admin_headers)
    assert del_res.status_code == 200
    assert len(client.get("/api/users").json()) == 1



def test_isolated_continue_watching_per_user():
    # User 1 (e.g. Mamma) and User 2 (e.g. Figlio)
    user1_id = 10
    user2_id = 20

    # User 1 watches Inception at 1500s (25 min)
    cw_service.save_progress(
        content_type="movie",
        content_id="42",
        title="Inception",
        position_seconds=1500,
        duration_seconds=7200,
        user_id=user1_id,
    )

    # User 2 watches Inception at 300s (5 min)
    cw_service.save_progress(
        content_type="movie",
        content_id="42",
        title="Inception",
        position_seconds=300,
        duration_seconds=7200,
        user_id=user2_id,
    )

    # Check list for user 1
    u1_list = cw_service.get_continue_watching_list(user_id=user1_id)
    assert len(u1_list) == 1
    assert u1_list[0]["position_seconds"] == 1500

    # Check list for user 2
    u2_list = cw_service.get_continue_watching_list(user_id=user2_id)
    assert len(u2_list) == 1
    assert u2_list[0]["position_seconds"] == 300

    # Deleting record for user 1 does not delete record for user 2
    cw_service.delete_item("movie", "42", user_id=user1_id)
    assert len(cw_service.get_continue_watching_list(user_id=user1_id)) == 0
    assert len(cw_service.get_continue_watching_list(user_id=user2_id)) == 1


def test_update_own_admin_user(client):
    models.set_setting(models.SETTING_AUTH_MODE, "local")
    admin = models.create_local_user("admin", "adminpwd", is_admin=True)

    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "adminpwd"})
    csrf = login_res.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    # Admin updates their own username and password
    update_res = client.put(
        f"/api/users/{admin.id}",
        json={"username": "newadmin", "password": "newpassword123", "is_admin": True, "parental_control": "adult"},
        headers=headers,
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["username"] == "newadmin"

    # Verify new credentials work on login
    client.post("/api/auth/logout", headers=headers)
    new_login = client.post("/api/auth/login", json={"username": "newadmin", "password": "newpassword123"})
    assert new_login.status_code == 200
    assert new_login.json()["user"]["username"] == "newadmin"

