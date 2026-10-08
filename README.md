# jellyfin-invite

Invite and onboarding app for Pierce's Jellyfin and Jellyseerr setup, served at
https://join.levangie.dev.

## User flow

1. Admin creates an invite at `/admin` (bearer `ADMIN_TOKEN`). Invites expire
   after 1–90 days and allow 1–25 uses.
2. User opens `/j/<code>` and either:
   - **Continue with Google**: Keycloak OIDC (`kc_idp_hint=google`), callback
     `/oidc/callback`. The verified Keycloak user is added to
     `KEYCLOAK_GROUP_ID`.
   - **Use email instead**: creates or finds the Keycloak user, adds it to
     the group, and sends a verify-email/set-password link.
3. Successful invite sign-in returns to the walkthrough at `/` with verified
   sign-in confirmation. Existing users can practice **Sign in with SSO** there;
   this opens Keycloak without a Google hint and does not redeem an invite or
   grant access. Confirmation lasts one hour in a signed HttpOnly cookie.
4. The guide walks through installing Seerr (`REQUESTS_URL`) in Safari or
   Chrome, then Jellyfin login using the supplied screenshots and TV Quick
   Connect. Installation must happen on Seerr itself; this separate guide
   cannot trigger or detect Seerr installation.
5. Group `jellyfin-users` grants the realm role checked by Jellyfin's SSO
   plugin. Use **Sign in with Keycloak** in Jellyfin and Seerr. Explicit guide
   section links are bookmarkable; Home always opens Welcome.

## Configuration

| Variable | Default |
| --- | --- |
| `ADMIN_TOKEN`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_GROUP_ID` | required |
| `KEYCLOAK_BASE` / `KEYCLOAK_REALM` | `https://auth.levangie.org` / `master` |
| `PUBLIC_BASE_URL` | `https://join.levangie.dev` |
| `OIDC_REDIRECT_URI` | `$PUBLIC_BASE_URL/oidc/callback` |
| `OIDC_IDP_HINT` | `google` (empty shows the Keycloak login page) |
| `JELLYFIN_URL` | `https://jellyfin.levangie.org` |
| `REQUESTS_URL` | `https://request.levangie.dev` |
| `DB_PATH` | `/data/invites.sqlite3` |

The Keycloak client needs standard flow, the exact redirect URI above, and a
service account allowed to query users, manage group membership and send
action emails.

Deployment lives in `home-infra` at `argocd/manifests/jellyfin-invite`;
secrets come from an ExternalSecret.

## Local development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
export ADMIN_TOKEN=test-admin KEYCLOAK_CLIENT_ID=test-client \
  KEYCLOAK_CLIENT_SECRET=test-secret KEYCLOAK_GROUP_ID=test-group \
  DB_PATH=/tmp/jellyfin-invite.sqlite3
flask --app 'app:create_app()' run --port 8080
pytest
```

## Release

Pushing `main` (or a `v*` tag) builds `ghcr.io/jlevangi/jellyfin-invite` via
GitHub Actions. Update the `sha-<commit>` image tag in `home-infra`.
