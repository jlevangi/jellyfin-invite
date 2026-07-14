from flask import Flask

from .config import Config
from .routes import bp
from .security import add_security_headers


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.after_request(add_security_headers)
    app.register_blueprint(bp)
    return app
