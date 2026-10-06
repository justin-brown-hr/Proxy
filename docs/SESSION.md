# Session save — University Library Proxy

**Saved:** 2026-10-06  
**Branch:** `main`  
**Last commit:** `6938a98` — update  
**Purpose:** resume work after moving workspace / new Cursor chat

---

## Project in one line

Dockerized EZproxy-style library proxy: Nginx + Keycloak + oauth2-proxy + guest portal + LDAP/Office365-ready auth + stanzas for publishers + Metabase analytics.

**Production:** https://proxy.bibliolatino.com  
**Egress IP (whitelist publishers):** `169.58.217.137`

---

## Milestone status

| Milestone | Status | What |
|-----------|--------|------|
| M1 | Done | Nginx + Keycloak + oauth2-proxy + SSO |
| M2 | Done | ScienceDirect, Scopus, IOP + simulator |
| M3 | Done | Guest register + admin approval |
| M4 | In progress | LDAP + log pipeline → Metabase |

---

## What was done in recent sessions

1. **Documentation & training package**
   - `docs/manual-y-capacitacion.md` — full technical + ops + training (modules A–G)
   - `docs/Manual-Tecnico-Operativo-y-Capacitacion.docx` — Word handover
   - `docs/Capacitacion-University-Library-Proxy.pptx` — training deck
   - README updated to link these deliverables

2. **Video guide materials**
   - In git: `Guion-Video-Guia.md`, `Guia-Video-Capitulos.txt`
   - Local only (gitignored): `*.mp4`, `*.srt` — e.g. `docs/Guia-Video-Bibliolatino-Proxy.mp4`, root demo video
   - Also gitignored: `sshpass_*.deb`, `docs/chathistory.md`

3. **Client conversation (Sep 2026)**
   - Client said docs/PPT are complementary, not the live training itself
   - Asked about switching auth from LDAP → **Office 365 / Entra ID**
   - Asked about adding **1–2 extra DBs** (likely EBSCO)
   - Draft reply given: Office365 via Keycloak IdP; new bases via stanzas; extra work = paid add-on
   - Do **not** push training-schedule promises in client replies unless asked

4. **Earlier ops help**
   - Metabase wizard is PostgreSQL → DB `analytics` (not library MySQL)
   - Demo admin for guest approval: `librarian` / `admin123`
   - Realm: `library`

---

## Architecture quick map

```
Browser → Nginx :443
  /oauth2/*     → oauth2-proxy → Keycloak (OIDC)
  /guest/       → guest-portal (public register)
  /guest/admin  → SSO + role admin → guest-portal
  /metabase/    → Metabase
  /databases.html, /r/<name>/ → auth-gate → publishers / simulator
  /admin/       → Keycloak admin

Nginx access log → log-worker → Postgres `analytics.access_events` → Metabase
```

Auth gate: campus IP bypass (`INSTITUTIONAL_CIDRS`) OR oauth2-proxy session.

---

## Key paths

| Path | Role |
|------|------|
| `docker-compose.yml` | All services |
| `stanzas/*.yml` | Publisher configs |
| `scripts/generate-proxy-conf.py` | Build nginx locations + databases.html |
| `scripts/render-campus-geo.sh` | Campus IP geo file |
| `scripts/configure-guest-portal.sh` | Guest portal KC roles |
| `scripts/configure-ldap-federation.sh` | LDAP federation |
| `scripts/validate-m1.sh` … `validate-m4.sh` | Smoke tests |
| `guest-portal/` | FastAPI register/approve |
| `log-worker/` | Log → Postgres |
| `keycloak/import/library-realm.json` | Realm import |
| `.env.example` | Env template (no secrets) |
| `docs/credentials.env` | **Local secrets — gitignored, do not commit** |

---

## Pending / next likely work

1. Finish / harden **M4** (Metabase setup on prod if still wizard-only; LDAP optional)
2. If client confirms: configure **Microsoft Entra ID (Office 365)** as Keycloak Identity Provider
   - Need: tenant ID, app Client ID/secret, admin consent, email domain, group scope
3. If client confirms: add **EBSCO** (+ maybe one more) stanza + publisher IP whitelist
4. Live training session / recording (client still expects the session itself, not only materials)
5. Extra DBs / Office365 = likely **paid add-on** vs original $1,400 / M1–M4 scope (`docs/detail.md`)

---

## Git state when this file was written

- Branch tracking `origin/main`
- Staged/modified (ready to commit when you choose):
  - `README.md` (modified)
  - Docs package: md, docx, pptx, video guide files, mp4/srt
  - Large video at repo root may also be staged — check size before push
- **Do not commit:** `.env`, `docs/credentials.env`, real secrets

Suggested commit message if you push docs only:

```
docs: add handover manual, training deck, video guide, and session resume file
```

---

## How to resume in a new workspace

```bash
git clone <repo-url> Proxy
cd Proxy
cp .env.example .env   # restore secrets from password manager / credentials.env backup
# optional: restore docs/credentials.env outside git
docker compose up -d
```

Then open `docs/SESSION.md` + `docs/manual-y-capacitacion.md` for full context.

---

## Demo accounts (realm `library`)

| User | Password | Roles |
|------|----------|-------|
| demo | demo123 | user |
| librarian | admin123 | user, admin |

Rotate before final campus handover.

---

*End of session file.*
