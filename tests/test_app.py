import urllib.parse

import app.routes as routes


class FakeKeycloak:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def activate(self, email):
        self.calls.append(email)
        return True

    def exchange_code(self, code, redirect_uri):
        self.calls.append(("exchange", code, redirect_uri))
        return {"access_token": "test-access"}

    def userinfo(self, access_token):
        self.calls.append(("userinfo", access_token))
        return {"sub": "keycloak-user-id", "email": "USER@Example.Test", "email_verified": True}

    def grant_existing_user(self, user_id):
        self.calls.append(("grant", user_id))


def auth():
    return {"X-Admin-Token": "test-admin"}


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.text == "ok\n"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in res.headers["Content-Security-Policy"]


def test_guide_page_renders_core_sections(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b'href="/admin">Admin Login</a>' in res.data
    assert b"Watch Jellyfin. Request new media." in res.data
    assert b"QuickConnect" in res.data
    assert b"Add Requests or Jellyfin to your home screen" in res.data
    assert b"https://jellyfin.example.test" in res.data
    assert b"https://request.example.test" in res.data


def test_join_page_renders_code_and_no_direct_app_buttons(client):
    res = client.get("/j/abc123")
    assert res.status_code == 200
    assert b'href="/">Home</a>' in res.data
    assert b'href="/admin">Admin Login</a>' in res.data
    assert b"Continue with Google" in res.data
    assert b"Use email instead" in res.data
    assert b"Email me a password setup link" in res.data
    assert b'value="ABC123"' in res.data
    assert b"Continue to Jellyfin setup guide" in res.data
    assert b"Open Jellyfin" not in res.data
    assert b"Open Requests" not in res.data


def test_admin_requires_token(client):
    page = client.get("/admin")
    assert b"Admin password" in page.data
    assert b"Invite note" in page.data
    assert b"Expires after" in page.data
    assert b"days" in page.data

    res = client.get("/api/admin/invites")
    assert res.status_code == 401
    assert res.json == {"ok": False, "message": "Unauthorized"}


def test_admin_create_list_and_revoke_invite(client):
    created = client.post("/api/admin/invites", json={"note": "friend", "expiresDays": 7}, headers=auth())
    assert created.status_code == 200
    assert created.json["ok"] is True
    assert created.json["url"].startswith("https://join.example.test/j/")
    code = created.json["code"]

    listed = client.get("/api/admin/invites", headers=auth())
    assert listed.status_code == 200
    assert listed.json["invites"][0]["code"] == code
    assert listed.json["invites"][0]["note"] == "friend"

    revoked = client.post(f"/api/admin/invites/{code}/revoke", headers=auth())
    assert revoked.status_code == 200
    listed = client.get("/api/admin/invites", headers=auth())
    assert listed.json["invites"][0]["revoked_at"] is not None


def test_activation_rejects_bad_inputs(client):
    assert client.post("/api/activate", json={}).status_code == 400
    assert client.post("/api/activate", json={"email": "bad@", "code": "missing"}).status_code == 400
    assert client.post("/api/activate", json={"email": "a@example.test", "code": "missing"}).status_code == 403


def test_oversized_json_is_rejected(client):
    res = client.post("/api/activate", json={"email": "a@example.test", "code": "x" * 20000})
    assert res.status_code == 413


def test_activation_marks_invite_used(client, monkeypatch):
    monkeypatch.setattr(routes, "Keycloak", FakeKeycloak)
    FakeKeycloak.calls.clear()
    created = client.post("/api/admin/invites", json={"note": "friend"}, headers=auth())
    code = created.json["code"]

    res = client.post("/api/activate", json={"email": "USER@Example.Test", "code": code.lower()})
    assert res.status_code == 200
    assert res.json["ok"] is True
    assert res.json["created"] is True
    assert FakeKeycloak.calls == ["user@example.test"]

    listed = client.get("/api/admin/invites", headers=auth())
    invite = listed.json["invites"][0]
    assert invite["used_at"] is not None
    assert invite["used_by_email"] == "user@example.test"

    reused = client.post("/api/activate", json={"email": "other@example.test", "code": code})
    assert reused.status_code == 403


def test_oidc_invite_flow_grants_existing_keycloak_user(client, monkeypatch):
    monkeypatch.setattr(routes, "Keycloak", FakeKeycloak)
    FakeKeycloak.calls.clear()
    created = client.post("/api/admin/invites", json={"note": "google user"}, headers=auth())
    code = created.json["code"]

    start = client.get(f"/oidc/start/{code}")
    assert start.status_code == 302
    redirect = urllib.parse.urlparse(start.headers["Location"])
    params = urllib.parse.parse_qs(redirect.query)
    assert params["kc_idp_hint"] == ["google"]
    assert params["redirect_uri"] == ["https://join.example.test/oidc/callback"]

    callback = client.get("/oidc/callback?" + urllib.parse.urlencode({"code": "oidc-code", "state": params["state"][0]}))
    assert callback.status_code == 200
    assert b"Access granted" in callback.data
    assert ("grant", "keycloak-user-id") in FakeKeycloak.calls

    listed = client.get("/api/admin/invites", headers=auth())
    invite = listed.json["invites"][0]
    assert invite["used_by_email"] == "user@example.test"
    assert invite["used_by_subject"] == "keycloak-user-id"
