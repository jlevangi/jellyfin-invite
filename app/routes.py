import datetime as dt
import re
import secrets
import urllib.parse

from flask import Blueprint, current_app, jsonify, redirect, render_template, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .db import connect, now, rows
from .keycloak import Keycloak

bp = Blueprint("main", __name__)
EMAIL_RE = re.compile(r"^[^@\s]{1,254}@[^@\s]{1,253}\.[^@\s]{2,63}$")


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


def state_serializer():
    return URLSafeTimedSerializer(current_app.config["ADMIN_TOKEN"], salt="jellyfin-invite-oidc")


def need_admin():
    token = request.headers.get("X-Admin-Token") or request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not secrets.compare_digest(token, current_app.config["ADMIN_TOKEN"]):
        return jsonify(ok=False, message="Unauthorized"), 401
    return None


def invite_is_invalid(con, invite):
    if not invite or invite["revoked_at"] or invite["expires_at"] <= now():
        return True
    use_count = con.execute(
        """select
           (select count(*) from invite_redemptions where invite_code=?) +
           (select count(*) from invite_reservations where invite_code=?)""",
        (invite["code"], invite["code"]),
    ).fetchone()[0]
    return use_count >= invite["max_uses"]


def reserve_redemption(code):
    reservation = secrets.token_urlsafe(18)
    with get_db() as con:
        con.execute("begin immediate")
        invite = con.execute("select * from invite_codes where code=?", (code,)).fetchone()
        if invite_is_invalid(con, invite):
            return None
        con.execute(
            "insert into invite_reservations(id,invite_code,created_at) values(?,?,?)",
            (reservation, code, now()),
        )
    return reservation


def release_reservation(reservation):
    with get_db() as con:
        con.execute("delete from invite_reservations where id=?", (reservation,))


def record_redemption(reservation, code, email, subject=None):
    redeemed_at = now()
    with get_db() as con:
        con.execute("begin immediate")
        claimed = con.execute(
            "delete from invite_reservations where id=? and invite_code=?", (reservation, code)
        )
        if claimed.rowcount != 1:
            raise RuntimeError("Invite reservation was lost")
        con.execute(
            "insert into invite_redemptions(invite_code,redeemed_at,email,subject) values(?,?,?,?)",
            (code, redeemed_at, email, subject),
        )
        con.execute(
            """update invite_codes set used_at=coalesce(used_at,?),
               used_by_email=coalesce(used_by_email,?), used_by_subject=coalesce(used_by_subject,?)
               where code=?""",
            (redeemed_at, email, subject, code),
        )


def bounded_integer(data, key, default, minimum, maximum):
    value = data.get(key, default)
    if type(value) is str and value.isascii() and value.isdigit():
        value = int(value)
    if type(value) is not int:
        return None
    return value if minimum <= value <= maximum else None


def success_message():
    return (
        "Jellyfin access granted.\n\n"
        "Your account is ready for:\n"
        f"- {current_app.config['JELLYFIN_URL']}\n"
        f"- {current_app.config['REQUESTS_URL']}"
    )


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


@bp.get("/oidc/start/<code>")
def oidc_start(code):
    code = code.strip().upper()
    with get_db() as con:
        invite = con.execute("select * from invite_codes where code=?", (code,)).fetchone()
        invalid = invite_is_invalid(con, invite)
    if invalid:
        return render_template("join.html", code=code, error="Invite code is invalid, expired, used, or revoked."), 403

    state = state_serializer().dumps({"code": code, "nonce": secrets.token_urlsafe(16)})
    params = {
        "client_id": current_app.config["KEYCLOAK_CLIENT_ID"],
        "redirect_uri": current_app.config["OIDC_REDIRECT_URI"],
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }
    if current_app.config["OIDC_IDP_HINT"]:
        params["kc_idp_hint"] = current_app.config["OIDC_IDP_HINT"]
    auth_url = (
        f"{current_app.config['KEYCLOAK_BASE'].rstrip('/')}/realms/{current_app.config['KEYCLOAK_REALM']}"
        f"/protocol/openid-connect/auth?{urllib.parse.urlencode(params)}"
    )
    return redirect(auth_url)


@bp.get("/oidc/callback")
def oidc_callback():
    if request.args.get("error"):
        return render_template("join.html", code="", error="Keycloak login was cancelled or failed."), 400
    try:
        state = state_serializer().loads(request.args.get("state", ""), max_age=900)
    except SignatureExpired:
        return render_template("join.html", code="", error="Invite login expired. Open your invite link and try again."), 400
    except BadSignature:
        return render_template("join.html", code="", error="Invite login state was invalid. Open your invite link and try again."), 400

    code = state["code"]
    kc = keycloak()
    token = kc.exchange_code(request.args.get("code", ""), current_app.config["OIDC_REDIRECT_URI"])
    user = kc.userinfo(token["access_token"])
    email = (user.get("email") or "").lower()
    subject = user.get("sub")
    if not subject or not email or user.get("email_verified") is False:
        return render_template("join.html", code=code, error="Keycloak did not return a verified email for this account."), 403

    reservation = reserve_redemption(code)
    if not reservation:
        return render_template("join.html", code=code, error="Invite code is invalid, expired, used, or revoked."), 403
    try:
        kc.grant_existing_user(subject)
    except Exception:
        release_reservation(reservation)
        raise
    record_redemption(reservation, code, email, subject)
    return render_template("success.html", message=success_message())


@bp.get("/admin")
def admin():
    return render_template("admin.html")


@bp.post("/api/admin/invites")
def create_invite():
    auth = need_admin()
    if auth:
        return auth
    data = request.get_json(silent=True) or {}
    days = bounded_integer(data, "expiresDays", 14, 1, 90)
    max_uses = bounded_integer(data, "maxUses", 1, 1, 25)
    if days is None or max_uses is None:
        return jsonify(ok=False, message="Expiry must be 1–90 days and maximum uses must be 1–25."), 400
    code = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12].upper()
    expires = (dt.datetime.now(dt.UTC) + dt.timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with get_db() as con:
        con.execute(
            "insert into invite_codes(code,note,created_at,expires_at,max_uses) values(?,?,?,?,?)",
            (code, str(data.get("note", ""))[:200], now(), expires, max_uses),
        )
    return jsonify(ok=True, code=code, url=f"{current_app.config['PUBLIC_BASE_URL']}/j/{code}")


@bp.get("/api/admin/invites")
def list_invites():
    auth = need_admin()
    if auth:
        return auth
    with get_db() as con:
        invites = rows(con.execute("select * from invite_codes order by created_at desc limit 200"))
        for invite in invites:
            invite["redemptions"] = rows(con.execute(
                "select redeemed_at,email,subject from invite_redemptions where invite_code=? order by id",
                (invite["code"],),
            ))
            invite["use_count"] = len(invite["redemptions"])
        return jsonify(ok=True, invites=invites)


@bp.post("/api/admin/invites/<code>/revoke")
def revoke_invite(code):
    auth = need_admin()
    if auth:
        return auth
    with get_db() as con:
        con.execute(
            "update invite_codes set revoked_at=coalesce(revoked_at,?) where code=?",
            (now(), code.upper()),
        )
    return jsonify(ok=True)


@bp.post("/api/activate")
def activate():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip().upper()
    if not EMAIL_RE.fullmatch(email) or not code:
        return jsonify(ok=False, message="Email and invite code are required."), 400
    reservation = reserve_redemption(code)
    if not reservation:
        return jsonify(ok=False, message="Invite code is invalid, expired, used, or revoked."), 403
    try:
        created = keycloak().activate(email)
    except Exception:
        release_reservation(reservation)
        raise
    record_redemption(reservation, code, email)
    return jsonify(ok=True, created=created, message=success_message())
