import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("ADMIN_TOKEN", "test-admin")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test-client")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test-secret")
os.environ.setdefault("KEYCLOAK_GROUP_ID", "test-group")

from app import create_app


class TestConfig:
    TESTING = True
    DB_PATH = ""
    ADMIN_TOKEN = "test-admin"
    KEYCLOAK_CLIENT_ID = "test-client"
    KEYCLOAK_CLIENT_SECRET = "test-secret"
    KEYCLOAK_GROUP_ID = "test-group"
    KEYCLOAK_BASE = "https://auth.example.test"
    KEYCLOAK_REALM = "master"
    MAX_CONTENT_LENGTH = 16 * 1024
    PUBLIC_BASE_URL = "https://join.example.test"
    OIDC_REDIRECT_URI = "https://join.example.test/oidc/callback"
    OIDC_IDP_HINT = "google"
    JELLYFIN_URL = "https://jellyfin.example.test"
    REQUESTS_URL = "https://request.example.test"


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    TestConfig.DB_PATH = path
    app = create_app(TestConfig)
    with app.test_client() as c:
        yield c
    os.unlink(path)
