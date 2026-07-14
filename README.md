# jellyfin-invite

Small invite and onboarding app for Pierce's Jellyfin/Seerr setup.

## Local development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
export ADMIN_TOKEN=test-admin
export KEYCLOAK_CLIENT_ID=test-client
export KEYCLOAK_CLIENT_SECRET=test-secret
export KEYCLOAK_GROUP_ID=test-group
export DB_PATH=/tmp/jellyfin-invite.sqlite3
flask --app 'app:create_app()' run --port 8080
```

## Tests

```bash
pytest
```

## Image

```bash
docker build -t ghcr.io/jlevangi/jellyfin-invite:0.1.0 .
docker push ghcr.io/jlevangi/jellyfin-invite:0.1.0
```
