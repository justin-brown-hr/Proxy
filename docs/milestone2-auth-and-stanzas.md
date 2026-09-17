# Milestone 2 — authentication methods (Keycloak)

The proxy gate (Nginx `auth_request`) always consumes a **validated OIDC session**
from oauth2-proxy → Keycloak. Additional campus protocols are attached **as
Keycloak identity providers / clients**, not as separate Nginx plugins.

## IP (campus allowlist)

1. Set `INSTITUTIONAL_CIDRS` in `.env` (comma-separated CIDRs).
2. Run `./scripts/render-campus-geo.sh` and reload Nginx.
3. Requests from those IPs skip SSO (`/auth-gate` returns 200 as `campus-ip`).

Remote users still authenticate via Keycloak.

## OAuth2 / OpenID Connect

Already live (Milestone 1): client `library-proxy`, realm `library`.

## SAML 2.0

In Keycloak Admin → Realm **library** → Identity providers → **Add SAML**:

- Import IdP metadata URL or XML from the university IdP
- Set NameID policy / mappers for email and username
- Users land in the same realm; Nginx still sees one OIDC token

## CAS

Keycloak → Identity providers → **CAS**:

- CAS server base URL
- Map `cas:user` → username / email

## LTI (Canvas / Moodle)

Use Keycloak as OIDC/OAuth tool provider, or add an LTI broker that federates into
the `library` realm. Practical path for libraries:

1. LMS launches via LTI 1.3 → platform registers Keycloak (or a thin LTI gateway)
2. Gateway exchanges LTI claims for a Keycloak user session (same realm)
3. User is redirected to `https://proxy…/databases.html` with SSO cookie set

Detailed LMS client registration is institution-specific; the proxy path stays OIDC.

## LDAP / Microsoft Entra / Google

Keycloak User federation (LDAP) or Identity providers (OIDC to Entra / Google).
Email linking avoids duplicate metrics (as discussed in Milestone 1).

## Adding a new publisher database

1. Copy `stanzas/simulator.yml` → `stanzas/<name>.yml`
2. Set `target`, `host_header`, and `find_replace` rules
3. `PUBLIC_HOST=… PUBLIC_SCHEME=https ./scripts/generate-proxy-conf.py`
4. `docker compose exec nginx nginx -s reload` (or recreate nginx)

Live Elsevier/IOP targets need the proxy egress IP whitelisted first.
