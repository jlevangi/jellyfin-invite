import datetime as dt
import re
import secrets
import urllib.parse

from flask import Blueprint, current_app, jsonify, make_response, redirect, render_template, request
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


def auth_serializer():
    return URLSafeTimedSerializer(current_app.config["ADMIN_TOKEN"], salt="jellyfin-walkthrough-auth")


def admin_session_serializer():
    return URLSafeTimedSerializer(current_app.config["ADMIN_TOKEN"], salt="jellyfin-admin-session")




def admin_session():
    try:
        session = admin_session_serializer().loads(request.cookies.get("admin_session", ""), max_age=3600)
    except (BadSignature, SignatureExpired):
        return None
    if session.get("sub") not in current_app.config.get("KEYCLOAK_ADMIN_SUBJECTS", ()):
        return None
    return session


def need_admin(write=False):
    token = request.headers.get("X-Admin-Token") or request.headers.get("Authorization", "").removeprefix("Bearer ")
    if token and secrets.compare_digest(token, current_app.config["ADMIN_TOKEN"]):
        return None
    session = admin_session()
    if session:
        if write and not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf", "")):
            return jsonify(ok=False, message="CSRF validation failed"), 403
        return None
    return jsonify(ok=False, message="Unauthorized"), 401


def _admin_failure(message):
    response = redirect("/invite?error=" + urllib.parse.quote(message, safe=""))
    response.delete_cookie("oidc_browser", path="/oidc/callback")
    return response




def _admin_state(state):
    return isinstance(state, dict) and state.get("purpose") == "admin"

def _oidc_failure(message, code=""):
    response = make_response(render_template("join.html", code=code, error=message), 400)
    response.delete_cookie("oidc_browser", path="/oidc/callback")
    return response


@bp.get("/healthz")
def healthz():
    return "ok\n"


@bp.get("/")
def onboarding():
    authenticated = False
    try:
        auth = auth_serializer().loads(request.cookies.get("walkthrough_auth", ""), max_age=3600)
        authenticated = bool(auth.get("sub"))
    except (BadSignature, SignatureExpired):
        pass
    return render_template("guide.html", jellyfin_url=current_app.config["JELLYFIN_URL"],
                           requests_url=current_app.config["REQUESTS_URL"], authenticated=authenticated)


@bp.get("/j/<code>")
def join(code):
    return render_template("join.html", code=code.upper())


def _oidc_redirect(state, nonce):
    params = {"client_id": current_app.config["KEYCLOAK_CLIENT_ID"], "redirect_uri": current_app.config["OIDC_REDIRECT_URI"],
              "response_type": "code", "scope": "openid email profile", "state": state, "nonce": nonce}
    auth_url = (f"{current_app.config['KEYCLOAK_BASE'].rstrip('/')}/realms/{current_app.config['KEYCLOAK_REALM']}"
                f"/protocol/openid-connect/auth?{urllib.parse.urlencode(params)}")
    response = redirect(auth_url)
    response.set_cookie("oidc_browser", nonce, max_age=900, httponly=True, secure=request.is_secure,
                        samesite="Lax", path="/oidc/callback")
    return response


@bp.get("/oidc/sign-in")
def oidc_sign_in():
    return oidc_start(None)


@bp.get("/oidc/start/<code>")
def oidc_start(code):
    is_sign_in = code is None
    code = "" if is_sign_in else code.strip().upper()
    if not is_sign_in:
        with get_db() as con:
            invite = con.execute("select * from invite_codes where code=?", (code,)).fetchone()
            invalid = invite_is_invalid(con, invite)
        if invalid:
            return render_template("join.html", code=code, error="Invite code is invalid, expired, used, or revoked."), 403
    nonce = secrets.token_urlsafe(16)
    state = state_serializer().dumps({"code": code or None, "nonce": nonce, "purpose": "invite" if code else "walkthrough"})
    response = _oidc_redirect(state, nonce)
    if code and current_app.config["OIDC_IDP_HINT"]:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(response.location).query)
        params["kc_idp_hint"] = [current_app.config["OIDC_IDP_HINT"]]
        response.location = response.location.split("?", 1)[0] + "?" + urllib.parse.urlencode(params, doseq=True)
    return response


@bp.get("/invite/oidc")
def admin_oidc():
    if not current_app.config.get("KEYCLOAK_ADMIN_SUBJECTS", ()):
        return _admin_failure("Admin sign-in is not configured")
    nonce = secrets.token_urlsafe(16)
    state = state_serializer().dumps({"code": None, "nonce": nonce, "purpose": "admin"})
    return _oidc_redirect(state, nonce)


@bp.get("/oidc/callback")
def oidc_callback():
    try:
        state = state_serializer().loads(request.args.get("state", ""), max_age=900)
    except SignatureExpired:
        return _oidc_failure("Sign-in expired. Return to the guide or reopen your invite and try again.")
    except BadSignature:
        return _oidc_failure("Sign-in state was invalid. Return to the guide or reopen your invite and try again.")
    if not isinstance(state, dict):
        return _oidc_failure("Sign-in state was invalid or expired.")
    is_admin = _admin_state(state)
    code = state.get("code")
    if not state.get("nonce") or not secrets.compare_digest(request.cookies.get("oidc_browser", ""), state["nonce"]):
        if is_admin:
            return _admin_failure("Admin sign-in session did not match. Try again.")
        response = make_response(render_template("join.html", code=code or "", error="This sign-in started in another browser session. Return to the guide or reopen your invite and try again."), 400)
        response.delete_cookie("oidc_browser", path="/oidc/callback")
        return response
    if request.args.get("error") or not request.args.get("code"):
        if is_admin:
            return _admin_failure("Keycloak sign-in was cancelled or failed")
        response = make_response(render_template("join.html", code=code or "", error="Keycloak sign-in was cancelled or failed. Return to the guide or reopen your invite and try again."), 400)
        response.delete_cookie("oidc_browser", path="/oidc/callback")
        return response
    try:
        kc = keycloak()
        token = kc.exchange_code(request.args["code"], current_app.config["OIDC_REDIRECT_URI"])
        user = kc.userinfo(token["access_token"])
    except Exception:
        if is_admin:
            return _admin_failure("Keycloak sign-in failed")
        response = make_response(render_template("join.html", code=code or "", error=f"Keycloak sign-in failed. Return to the {'guide' if code is None else 'invite'} and try again."), 502)
        response.delete_cookie("oidc_browser", path="/oidc/callback")
        return response
    subject = user.get("sub")
    if is_admin:
        allowed = current_app.config.get("KEYCLOAK_ADMIN_SUBJECTS", ())
        if not subject or subject not in allowed:
            return _admin_failure("This Keycloak account is not authorized for admin access")
        csrf = secrets.token_urlsafe(32)
        response = redirect("/invite")
        response.set_cookie("admin_session", admin_session_serializer().dumps({"sub": subject, "csrf": csrf}), max_age=3600,
                            httponly=True, secure=request.is_secure, samesite="Lax", path="/")
        response.delete_cookie("oidc_browser", path="/oidc/callback")
        return response
    email = (user.get("email") or "").lower()
    if not subject or not email or user.get("email_verified") is not True:
        response = make_response(render_template("join.html", code=code or "", error="Keycloak did not return a verified email for this account."), 403)
        response.delete_cookie("oidc_browser", path="/oidc/callback")
        return response
    response = redirect("/#sign-in")
    response.delete_cookie("oidc_browser", path="/oidc/callback")
    if code is None:
        response.set_cookie("walkthrough_auth", auth_serializer().dumps({"sub": subject}), max_age=3600,
                            httponly=True, secure=request.is_secure, samesite="Lax", path="/")
        return response
    reservation = reserve_redemption(code)
    if not reservation:
        response = make_response(render_template("join.html", code=code, error="Invite code is invalid, expired, used, or revoked."), 403)
        response.delete_cookie("oidc_browser", path="/oidc/callback")
        return response
    try:
        kc.grant_existing_user(subject)
    except Exception:
        release_reservation(reservation)
        raise
    record_redemption(reservation, code, email, subject)
    response.set_cookie("walkthrough_auth", auth_serializer().dumps({"sub": subject}), max_age=3600,
                        httponly=True, secure=request.is_secure, samesite="Lax", path="/")
    return response


@bp.get("/invite")
def admin():
    return render_template("admin.html", oidc_enabled=bool(current_app.config.get("KEYCLOAK_ADMIN_SUBJECTS", ())), error=request.args.get("error", ""))


@bp.get("/api/admin/session")
def admin_session_status():
    session = admin_session()
    return jsonify(ok=True, authenticated=bool(session), csrfToken=session.get("csrf") if session else None)


@bp.post("/api/admin/logout")
def admin_logout():
    session = admin_session()
    if session:
        if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf", "")):
            return jsonify(ok=False, message="CSRF validation failed"), 403
    response = jsonify(ok=True)
    response.delete_cookie("admin_session", path="/")
    return response



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



@bp.post("/api/admin/invites")
def create_invite():
    auth = need_admin(write=True)
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
            invite["url"] = f"{current_app.config['PUBLIC_BASE_URL']}/j/{invite['code']}"
            invite["use_count"] = len(invite["redemptions"])
        return jsonify(ok=True, invites=invites)


@bp.post("/api/admin/invites/<code>/revoke")
def revoke_invite(code):
    auth = need_admin(write=True)
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
