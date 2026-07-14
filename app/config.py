import os


class Config:
    DB_PATH = os.environ.get("DB_PATH", "/data/invites.sqlite3")
    MAX_CONTENT_LENGTH = 16 * 1024
    ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
    KEYCLOAK_CLIENT_ID = os.environ["KEYCLOAK_CLIENT_ID"]
    KEYCLOAK_CLIENT_SECRET = os.environ["KEYCLOAK_CLIENT_SECRET"]
    KEYCLOAK_GROUP_ID = os.environ["KEYCLOAK_GROUP_ID"]
    KEYCLOAK_BASE = os.environ.get("KEYCLOAK_BASE", "https://auth.levangie.org")
    KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "master")
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://join.levangie.dev")
    JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "https://jellyfin.levangie.org")
    REQUESTS_URL = os.environ.get("REQUESTS_URL", "https://request.levangie.org")
