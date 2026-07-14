import datetime as dt
import secrets

from flask import Blueprint, current_app, jsonify, render_template, request

from .db import connect, now, rows
from .keycloak import Keycloak

bp = Blueprint("main", __name__)


def get_db():
    return connect(current_app.config["DB_PATH"])


def keycloak():
    return Keycloak(
        current_app.config["KEYCLOAK_BASE"],
        current_app.config["KEYCLOAK_REALM"],
        current_app.config["KEYCLOAK_CLIENT_ID"],
        current_app.config["KEYCLOAK_CLIENT_SECRET"],
        current_app.config["KEYCLOAK_GROUP_ID"],
    )


def need_admin():
    token = request.headers.get("X-Admin-Token") or request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not secrets.compare_digest(token, current_app.config["ADMIN_TOKEN"]):
        return jsonify(ok=False, message="Unauthorized"), 401
    return None


@bp.get("/healthz")
def healthz():
    return "ok\n"


@bp.get("/")
def onboarding():
    return render_template(
        "guide.html",
        jellyfin_url=current_app.config["JELLYFIN_URL"],
        requests_url=current_app.config["REQUESTS_URL"],
    )


@bp.get("/j/<code>")
def join(code):
    return render_template("join.html", code=code.upper())


@bp.get("/admin")
def admin():
    return render_template("admin.html")


@bp.post("/api/admin/invites")
def create_invite():
    auth = need_admin()
    if auth:
        return auth
    data = request.get_json(silent=True) or {}
    days = max(1, min(90, int(data.get("expiresDays") or 14)))
    code = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12].upper()
    expires = (dt.datetime.now(dt.UTC) + dt.timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with get_db() as con:
        con.execute(
            "insert into invite_codes(code,note,created_at,expires_at) values(?,?,?,?)",
            (code, data.get("note", "")[:200], now(), expires),
        )
    return jsonify(ok=True, code=code, url=f"{current_app.config['PUBLIC_BASE_URL']}/j/{code}")


@bp.get("/api/admin/invites")
def list_invites():
    auth = need_admin()
    if auth:
        return auth
    with get_db() as con:
        return jsonify(ok=True, invites=rows(con.execute("select * from invite_codes order by created_at desc limit 200")))


@bp.post("/api/admin/invites/<code>/revoke")
def revoke_invite(code):
    auth = need_admin()
    if auth:
        return auth
    with get_db() as con:
        con.execute(
            "update invite_codes set revoked_at=coalesce(revoked_at,?) where code=? and used_at is null",
            (now(), code.upper()),
        )
    return jsonify(ok=True)


@bp.post("/api/activate")
def activate():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip().upper()
    if "@" not in email or not code:
        return jsonify(ok=False, message="Email and invite code are required."), 400
    with get_db() as con:
        con.execute("begin immediate")
        invite = con.execute("select * from invite_codes where code=?", (code,)).fetchone()
        if not invite or invite["used_at"] or invite["revoked_at"] or invite["expires_at"] <= now():
            return jsonify(ok=False, message="Invite code is invalid, expired, used, or revoked."), 403
        created = keycloak().activate(email)
        con.execute("update invite_codes set used_at=?, used_by_email=? where code=?", (now(), email, code))
    return jsonify(
        ok=True,
        created=created,
        message=(
            "Account has been created, and Jellyfin access granted. Please check your email to set a password.\n\n"
            "You will sign in using Keycloak for:\n- jellyfin.levangie.org\n- request.levangie.org"
        ),
    )
