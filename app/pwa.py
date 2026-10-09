from flask import Blueprint, send_from_directory

bp = Blueprint("pwa", __name__)


@bp.get("/service-worker.js")
def service_worker():
    response = send_from_directory("static", "service-worker.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response
