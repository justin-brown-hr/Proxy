# University Library Proxy

Dockerized reverse-proxy stack with unified SSO (EZproxy-style).

## Documentation & training

Handover package (Spanish), covering architecture, install, SSO, stanzas, guest portal, LDAP,
Metabase, runbooks, troubleshooting and the hands-on training modules (A–G):

| Deliverable | Format | Audience |
|---|---|---|
| [docs/Manual-Tecnico-Operativo-y-Capacitacion.docx](docs/Manual-Tecnico-Operativo-y-Capacitacion.docx) | Word | Client handover — full manual, 17 sections |
| [docs/Capacitacion-University-Library-Proxy.pptx](docs/Capacitacion-University-Library-Proxy.pptx) | PowerPoint | Training support deck, 31 slides |
| [docs/manual-y-capacitacion.md](docs/manual-y-capacitacion.md) | Markdown | Same manual, for reading inside the repo |

## Milestones

| Milestone | Status | What |
|-----------|--------|------|
| **M1** | Done | Nginx + Keycloak + oauth2-proxy + SSO |
| **M2** | Done | Config-file rewrites: ScienceDirect, Scopus, IOP + simulator |
| **M3** | Done | Guest self-registration + admin approval |
| **M4** | In progress | LDAP federation + log pipeline → Metabase |

## Quick start

```bash
cp .env.example .env
# edit PUBLIC_HOST / APP_URL / secrets
./scripts/render-campus-geo.sh
PUBLIC_HOST=your.domain PUBLIC_SCHEME=https ./scripts/generate-proxy-conf.py
docker compose up -d
```

## Milestone 3 — guest registration

- Public form: `/guest/`
- Admin approval (role `admin`): `/guest/admin`
- Guests are created **disabled** via Keycloak Admin API (`guest_status=pending`)
- Approve enables the account — no Keycloak core patches

```bash
./scripts/configure-guest-portal.sh
./scripts/validate-m3.sh
```

Demo admin user for approvals: `librarian` / `admin123`

## Milestone 4 — LDAP + analytics

- OpenLDAP at `usuarios.bibliolatino.com` federated into Keycloak (`scripts/configure-ldap-federation.sh`)
- Guests mirrored into LDAP (`employeeType=pending|guest|rejected`) when LDAP env is set
- Nginx access log → `log-worker` → Postgres `analytics.access_events`
- Metabase: `https://<host>/metabase/` (setup wizard; add DB `postgres` / `analytics`)

```bash
# on proxy host, with docs/credentials.env or .env LDAP_* set
./scripts/configure-ldap-federation.sh
docker compose up -d --build log-worker metabase guest-portal
./scripts/validate-m4.sh
```

In Metabase, connect database: host `postgres`, db `analytics`, same user/password as Postgres. Export CSV/XML/PDF from any question/dashboard.

## Milestone 2 — publisher proxy

Access after SSO: `https://<host>/databases.html`

| Path | Target |
|------|--------|
| `/r/simulator/` | Local simulator (works now, no whitelist) |
| `/r/sciencedirect/` | www.sciencedirect.com (needs Elsevier IP allow) |
| `/r/scopus/` | www.scopus.com (needs Elsevier IP allow) |
| `/r/iop/` | iopscience.iop.org (needs IOP IP allow) |

**Add a database:** edit/add `stanzas/<name>.yml`, regenerate, reload nginx.

```bash
PUBLIC_HOST=proxy.bibliolatino.com PUBLIC_SCHEME=https ./scripts/generate-proxy-conf.py
docker compose exec nginx nginx -s reload
```

**Campus IP bypass:** set `INSTITUTIONAL_CIDRS` and run `./scripts/render-campus-geo.sh`.

See [docs/milestone2-auth-and-stanzas.md](docs/milestone2-auth-and-stanzas.md) for SAML / CAS / LTI / OAuth / LDAP.

## Validation

```bash
./scripts/validate-m1.sh
./scripts/validate-auth-flows.sh
./scripts/validate-m2.sh
```

## Production URLs (bibliolatino)

- SSO / home: https://proxy.bibliolatino.com/
- Databases: https://proxy.bibliolatino.com/databases.html
- Admin: https://proxy.bibliolatino.com/admin/
- Proxy egress IP to whitelist: **169.58.217.137**

## Demo accounts (realm `library`)

| Username   | Password  | Roles        |
|------------|-----------|--------------|
| demo       | demo123   | user         |
| librarian  | admin123  | user, admin  |
