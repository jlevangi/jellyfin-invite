import urllib.parse

from app import routes


class FakeKeycloak:
    subject = "admin-subject"
    calls = []

    def __init__(self, *args):
        pass

    def exchange_code(self, code, redirect_uri):
        self.calls.append(("exchange", code))
        return {"access_token": "access"}

    def userinfo(self, token):
        return {"sub": self.subject, "email": "admin@example.test", "email_verified": True}


def admin_login(client):
    start = client.get("/invite/oidc")
    params = urllib.parse.parse_qs(urllib.parse.urlparse(start.location).query)
    state = params["state"][0]
    return client.get("/oidc/callback?" + urllib.parse.urlencode({"code": "code", "state": state}))


def test_admin_oidc_allowlist_session_and_csrf(client, monkeypatch):
    FakeKeycloak.calls.clear()
    monkeypatch.setattr(routes, "Keycloak", FakeKeycloak)
    monkeypatch.setattr(FakeKeycloak, "subject", "admin-subject")
    logged_in = admin_login(client)
    assert logged_in.status_code == 302 and logged_in.location == "/invite"
    session = client.get("/api/admin/session").json
    assert session["ok"] and session["authenticated"] and isinstance(session["csrfToken"], str)
    assert client.post("/api/admin/invites", json={}).status_code == 403
    assert client.post("/api/admin/invites", json={}, headers={"X-CSRF-Token": session["csrfToken"]}).status_code == 200
    assert client.post("/api/admin/logout").status_code == 403
    response = client.post("/api/admin/logout", headers={"X-CSRF-Token": session["csrfToken"]})
    assert response.json == {"ok": True}
    assert "admin_session=;" in response.headers["Set-Cookie"]
    assert client.get("/api/admin/session").json["authenticated"] is False

def test_admin_oidc_rejects_nonce_mismatch_without_exchange(client, monkeypatch):
    FakeKeycloak.calls.clear()
    monkeypatch.setattr(routes, "Keycloak", FakeKeycloak)
    start = client.get("/invite/oidc")
    params = urllib.parse.parse_qs(urllib.parse.urlparse(start.location).query)
    client.delete_cookie("oidc_browser", domain="localhost", path="/oidc/callback")
    mismatch = client.get("/oidc/callback?" + urllib.parse.urlencode({"code": "code", "state": params["state"][0]}))
    assert mismatch.status_code == 302 and mismatch.location.startswith("/invite?error=")
    assert not FakeKeycloak.calls


def test_admin_oidc_rejects_expired_state(client, monkeypatch):
    from itsdangerous import SignatureExpired

    class ExpiredState:
        def loads(self, *args, **kwargs):
            raise SignatureExpired("expired")

    monkeypatch.setattr(routes, "state_serializer", lambda: ExpiredState())
    response = client.get("/oidc/callback?" + urllib.parse.urlencode({"code": "code", "state": "expired"}))
    assert response.status_code == 400
    assert not client.get("/api/admin/session").json["authenticated"]


def test_admin_oidc_denies_non_allowlisted_subject_without_membership_change(client, monkeypatch):
    FakeKeycloak.calls.clear()
    monkeypatch.setattr(routes, "Keycloak", FakeKeycloak)
    monkeypatch.setattr(FakeKeycloak, "subject", "ordinary-user")
    login = admin_login(client)
    assert login.status_code == 302 and login.location.startswith("/invite?error=")
    assert client.get("/api/admin/session").json["authenticated"] is False
    assert not any(call[0] == "grant" for call in FakeKeycloak.calls)


def test_admin_password_token_fallback(client):
    assert client.get("/api/admin/invites", headers={"X-Admin-Token": "test-admin"}).status_code == 200
    assert client.post("/api/admin/invites", json={}, headers={"X-Admin-Token": "test-admin"}).status_code == 200
