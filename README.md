# jellyfin-invite

Invite and onboarding app for Pierce's Jellyfin and Jellyseerr setup, served at
https://join.levangie.dev.

## User flow

1. Admin creates an invite at `/invite` (header **Invite** button; bearer `ADMIN_TOKEN` or Keycloak). Invites expire
   after 1–90 days and allow 1–25 uses.
2. User opens `/j/<code>` and either:
   - **Continue with Google**: Keycloak OIDC (`kc_idp_hint=google`), callback
     `/oidc/callback`. The verified Keycloak user is added to
     `KEYCLOAK_GROUP_ID`.
   - **Use email instead**: creates or finds the Keycloak user, adds it to
     the group, and sends a verify-email/set-password link.
3. Successful invite sign-in returns to the walkthrough at `/` with verified
   sign-in confirmation. Existing users can use **Sign in with SSO** there; this
   opens Keycloak without a Google hint and does not redeem an invite or grant
   access. Confirmation lasts one hour in a signed HttpOnly cookie.
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
| `KEYCLOAK_ADMIN_SUBJECTS` | empty (OIDC admin disabled) |
| `JELLYFIN_URL` | `https://jellyfin.levangie.org` |
| `REQUESTS_URL` | `https://request.levangie.dev` |
| `DB_PATH` | `/data/invites.sqlite3` |

The Keycloak client needs standard flow, the exact redirect URI above, and a
service account allowed to query users, manage group membership and send
action emails.

### Admin OIDC

Set `KEYCLOAK_ADMIN_SUBJECTS` to a comma-separated allowlist of stable Keycloak
subject (`sub`) IDs. It defaults to empty, which disables OIDC admin sign-in.
The `/invite/oidc` flow uses the existing `/oidc/callback`; allowed subjects get
a separate one-hour HttpOnly admin session. Ordinary Keycloak users never gain
admin access through group membership. Cookie-authenticated admin writes require
the `X-CSRF-Token` returned by `GET /api/admin/session`; bearer `ADMIN_TOKEN`
clients remain supported. Configure the Keycloak redirect URI as
`$PUBLIC_BASE_URL/oidc/callback` as before.

`GET /api/admin/invites` returns each invite's canonical URL using
`PUBLIC_BASE_URL`, matching the URL returned by invite creation.

The mobile dashboard uses invite cards with copy/revoke actions and expandable
redemption history. Password sign-in remains available alongside Keycloak.
On the Watching page, the top Web, Mobile, and TV buttons jump to bookmarkable
setup sections (`#jellyfin-website`, `#jellyfin-mobile`, `#jellyfin-tv`).

Deployment lives in `home-infra` at `argocd/manifests/jellyfin-invite`;
secrets come from an ExternalSecret.

## PWA

Pierce's Media installs as a standalone PWA. The brand links Home; the header
**Invite** button opens the invite dashboard at `/invite`. Offline mode
shows a network-required notice only. The service worker caches the shared
stylesheet, brand icon, and offline page; it never caches navigations or
private/admin/API/OIDC/invite responses.

Home displays the welcome banner at its original aspect ratio without cropping;
its feathered edges blend into the matching dark-navy page background (`#060d20`).

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
