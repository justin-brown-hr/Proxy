# Manual técnico, operativo y de capacitación

**Proyecto:** University Library Proxy (estilo EZproxy)  
**Stack:** Nginx · Keycloak · oauth2-proxy · Guest Portal · OpenLDAP · Postgres · Metabase  
**Audiencia:** equipo técnico in-house, bibliotecarios administradores y responsables de operación  
**Entorno de referencia:** `https://proxy.bibliolatino.com`

Este documento es el entregable de **handover**: explica la arquitectura, cómo instalar y operar el sistema, y cómo capacitar al equipo con ejercicios prácticos.

**Versiones entregables:** [Manual en Word](Manual-Tecnico-Operativo-y-Capacitacion.docx) · [Presentación de capacitación](Capacitacion-University-Library-Proxy.pptx)

---

## Índice

1. [Qué es y para qué sirve](#1-qué-es-y-para-qué-sirve)
2. [Arquitectura](#2-arquitectura)
3. [Componentes del sistema](#3-componentes-del-sistema)
4. [Instalación y primer arranque](#4-instalación-y-primer-arranque)
5. [Autenticación y SSO](#5-autenticación-y-sso)
6. [Bases de datos editoriales (stanzas)](#6-bases-de-datos-editoriales-stanzas)
7. [Portal de invitados](#7-portal-de-invitados)
8. [Federación LDAP](#8-federación-ldap)
9. [Analíticas y Metabase](#9-analíticas-y-metabase)
10. [Operación diaria (runbooks)](#10-operación-diaria-runbooks)
11. [Variables de entorno](#11-variables-de-entorno)
12. [Scripts de utilidad](#12-scripts-de-utilidad)
13. [Validación por hitos](#13-validación-por-hitos)
14. [Solución de problemas](#14-solución-de-problemas)
15. [Capacitación — módulos y ejercicios](#15-capacitación--módulos-y-ejercicios)
16. [Anexo: URLs, cuentas y checklist de entrega](#16-anexo-urls-cuentas-y-checklist-de-entrega)

---

## 1. Qué es y para qué sirve

El sistema es un **proxy inverso con autenticación unificada** para bibliotecas universitarias. Replica la idea central de EZproxy:

- El usuario se autentica **una sola vez** (SSO).
- Accede a bases de datos y revistas científicas **a través del proxy**.
- El proxy reescribe URLs para que enlaces, CSS, PDF y CDN sigan pasando por el dominio institucional.
- Desde la red del campus (IPs institucionales) se puede omitir el login.
- Invitados/egresados se auto-registran y un bibliotecario los aprueba.
- Los accesos se registran y se visualizan en Metabase (exportables a CSV, XML, PDF).

No es un sitio web de contenido: es **infraestructura** (red, identidad, seguridad y reescritura de URLs).

### Hitos del proyecto

| Hito | Estado | Contenido |
|------|--------|-----------|
| **M1** | Completado | Nginx + Keycloak + oauth2-proxy + SSO |
| **M2** | Completado | Reescrituras (ScienceDirect, Scopus, IOP) + simulador |
| **M3** | Completado | Registro de invitados + aprobación admin |
| **M4** | En curso / desplegable | LDAP + pipeline de logs → Metabase |

---

## 2. Arquitectura

### Diagrama de flujo

```
Navegador del usuario
        │
        ▼
   Nginx (:443 TLS)
        │
        ├── /realms/, /admin/, /resources/  → Keycloak
        ├── /oauth2/*                       → oauth2-proxy
        ├── /guest/ (público)               → Guest Portal
        ├── /guest/admin (protegido)        → auth-gate → Guest Portal
        ├── /metabase/                      → Metabase
        ├── /, /databases.html, /r/<db>/    → auth-gate → recursos
        └── /healthz                        → 200 OK

auth-gate:
  1) Si IP de campus → permitir sin SSO
  2) Si no → oauth2-proxy verifica cookie OIDC
  3) Si no hay sesión → redirigir a Keycloak (login)

Logs Nginx ──► log-worker ──► Postgres (analytics) ──► Metabase
```

### Servicios Docker (`docker-compose.yml`)

| Servicio | Contenedor | Función |
|----------|------------|---------|
| `postgres` | `library-postgres` | BD de Keycloak + `analytics` + `metabase` |
| `keycloak` | `library-keycloak` | Identity Provider (realm `library`) |
| `oauth2-proxy` | `library-oauth2-proxy` | Puente OIDC para `auth_request` de Nginx |
| `nginx` | `library-nginx` | Puerta TLS, auth, rutas y reescrituras |
| `test-resource` | `library-test-resource` | Página de inicio y catálogo `databases.html` |
| `publisher-simulator` | `library-publisher-simulator` | Editorial falsa para demos sin whitelist |
| `guest-portal` | `library-guest-portal` | Registro y aprobación de invitados (FastAPI) |
| `log-worker` | `library-log-worker` | Ingesta de access log → Postgres |
| `metabase` | `library-metabase` | Dashboards y exportación |

Red Docker: `library-net`. Volúmenes: `postgres_data`, `nginx_logs`.

### IP de salida (whitelist con editores)

Las bases **live** (Elsevier, IOP, etc.) deben autorizar la IP pública de egreso del proxy:

**`169.58.217.137`**

Sin esa whitelist, ScienceDirect / Scopus / IOP pueden fallar aunque el SSO funcione. El **simulador** no requiere whitelist.

---

## 3. Componentes del sistema

### 3.1 Nginx

- Termina HTTPS y enruta todo el tráfico público.
- Aplica `auth_request` vía ubicación interna `/auth-gate`.
- Genera el access log enriquecido (`library_access.log`) con usuario, email, campus y recurso.
- Las ubicaciones `/r/<nombre>/` se generan desde stanzas YAML (no se editan a mano de forma habitual).

Archivos clave:

- `nginx/nginx.conf` — formato de log y configuración global
- `nginx/conf.d/default.conf` — rutas principales
- `nginx/resources.locations.conf` — **generado** por `generate-proxy-conf.py`
- `nginx/campus-ip.geo.conf` — **generado** por `render-campus-geo.sh`

### 3.2 Keycloak (realm `library`)

- Roles: `user`, `admin`, `guest`
- Clientes:
  - `library-proxy` — OIDC para oauth2-proxy
  - `guest-portal` — service account para Admin API
- Registro público de Keycloak **deshabilitado** (los invitados usan el portal)
- Importación inicial: `keycloak/import/library-realm.json`

### 3.3 oauth2-proxy

- Valida la sesión OIDC y expone `/oauth2/auth` para Nginx.
- Cookie: `_library_oauth2`
- Cabeceras hacia backends: `X-Auth-Request-User`, `X-Auth-Request-Email`, etc.
- Config: `oauth2-proxy/oauth2-proxy.cfg`

### 3.4 Guest Portal

- App FastAPI en `guest-portal/`
- Formulario público de registro
- Panel admin (requiere rol `admin`)
- Crea usuarios en Keycloak **deshabilitados** hasta aprobación
- Opcionalmente los refleja en LDAP (`employeeType=pending|guest|rejected`)

### 3.5 Stanzas y generador

Cada base de datos es un YAML en `stanzas/`. El script `scripts/generate-proxy-conf.py` produce:

1. Reglas Nginx (`resources.locations.conf`)
2. Catálogo HTML (`test-resource/html/databases.html`)

### 3.6 Log-worker y Metabase

- `log-worker/worker.py` lee el access log y clasifica el tipo de contenido (`pdf`, `video`, `article`, …).
- Escribe en `analytics.access_events` y vistas `v_access_by_day`, `v_access_by_resource`.
- Metabase se sirve en `/metabase/` y consulta esa base.

---

## 4. Instalación y primer arranque

### Requisitos

- Docker y Docker Compose
- Dominio apuntando al servidor (producción)
- Puertos 80/443 libres
- (Opcional) acceso SSH al servidor LDAP para federación

### Pasos

```bash
cd /ruta/al/Proxy
cp .env.example .env
# Editar: PUBLIC_HOST, APP_URL, KEYCLOAK_PUBLIC_URL, secretos, LDAP si aplica

./scripts/render-campus-geo.sh
PUBLIC_HOST=proxy.bibliolatino.com PUBLIC_SCHEME=https ./scripts/generate-proxy-conf.py

# TLS (producción)
./scripts/issue-tls-cert.sh   # usa CERTBOT_EMAIL; detiene nginx brevemente

docker compose up -d

# Tras el primer boot de Keycloak (producción HTTPS):
./scripts/configure-public-access.sh
./scripts/configure-guest-portal.sh

# LDAP (si hay credenciales y servidor disponible):
./scripts/configure-ldap-federation.sh
```

### Comprobar salud

```bash
curl -fsS https://proxy.bibliolatino.com/healthz
docker compose ps
./scripts/validate-m1.sh
./scripts/validate-m2.sh
./scripts/validate-m3.sh
./scripts/validate-m4.sh
```

---

## 5. Autenticación y SSO

### Flujo remoto (fuera del campus)

1. El usuario abre `https://proxy.bibliolatino.com/` o `/databases.html`.
2. Nginx pide autorización a oauth2-proxy.
3. Sin cookie válida → redirección a Keycloak (login).
4. Tras login correcto → cookie OIDC → acceso al catálogo y a `/r/...`.

### Bypass por IP de campus

1. Definir CIDRs en `.env`:

   ```bash
   INSTITUTIONAL_CIDRS=10.0.0.0/8,192.168.0.0/16
   ```

2. Regenerar y recargar:

   ```bash
   ./scripts/render-campus-geo.sh
   docker compose exec nginx nginx -s reload
   ```

3. Desde esas IPs, `/auth-gate` responde 200 como acceso de campus (sin SSO).

### Métodos adicionales (SAML, CAS, LTI, Entra, Google)

El gate de Nginx **siempre** consume una sesión OIDC de oauth2-proxy → Keycloak.  
Protocolos institucionales se agregan **dentro de Keycloak** (Identity providers / User federation), no como plugins de Nginx.

Guía resumida: `docs/milestone2-auth-and-stanzas.md`.

| Protocolo | Dónde se configura |
|-----------|--------------------|
| OAuth2 / OIDC | Ya activo (`library-proxy`) |
| LDAP | User federation (script M4) |
| SAML 2.0 | Keycloak → Identity providers → SAML |
| CAS | Keycloak → Identity providers → CAS |
| LTI (Canvas/Moodle) | Broker LTI → sesión en realm `library` |
| Microsoft Entra / Google | Identity provider OIDC |

### Cuentas demo (realm `library`)

| Usuario | Contraseña | Roles |
|---------|------------|-------|
| `demo` | `demo123` | user |
| `librarian` | `admin123` | user, admin |

**Producción:** cambiar contraseñas y secretos antes de entrega final al campus.

### Cerrar sesión

Usar el flujo de sign-out de oauth2-proxy / Keycloak (validado por `validate-auth-flows.sh`). Tras logout, un recurso protegido debe volver a pedir autenticación.

---

## 6. Bases de datos editoriales (stanzas)

### Stanzas incluidas

| Stanza | Ruta | Destino | Notas |
|--------|------|---------|-------|
| `simulator` | `/r/simulator/` | Contenedor local | Demo sin whitelist |
| `sciencedirect` | `/r/sciencedirect/` | www.sciencedirect.com | Requiere IP allow |
| `scopus` | `/r/scopus/` | www.scopus.com | Requiere IP allow |
| `iop` | `/r/iop/` | iopscience.iop.org | Requiere IP allow |

Catálogo SSO: `https://proxy.bibliolatino.com/databases.html`

### Anatomía de un stanza

Ejemplo (`stanzas/simulator.yml`):

```yaml
name: simulator
title: Revista de demostración
description: Entorno de prueba...
enabled: true
mode: simulator          # live | simulator
target: http://publisher-simulator:80
host_header: publisher-simulator
start_path: /
find_replace:
  - find: "https://publisher.example/"
    replace: "{{PROXY_BASE}}/"
```

`{{PROXY_BASE}}` se sustituye por la URL pública del proxy (p. ej. `https://proxy.bibliolatino.com/r/simulator`).

### Cómo agregar una base nueva

1. Copiar `stanzas/simulator.yml` → `stanzas/<nombre>.yml`
2. Completar `name`, `title`, `target`, `host_header`, `find_replace`
3. Generar y recargar:

   ```bash
   PUBLIC_HOST=proxy.bibliolatino.com PUBLIC_SCHEME=https ./scripts/generate-proxy-conf.py
   docker compose exec nginx nginx -s reload
   ```

4. Si es `mode: live`, pedir a la editorial que whitelistée `169.58.217.137`
5. Verificar en `/databases.html` y en `/r/<nombre>/`

### Cómo funciona la reescritura

1. El usuario pide `/r/sciencedirect/...`
2. Nginx hace `proxy_pass` al origen real con el `Host` correcto
3. `sub_filter` reescribe enlaces absolutos del HTML para que apunten de nuevo al proxy
4. Así el usuario permanece en el dominio institucional durante la navegación

El **simulador** (`publisher-simulator`) sirve HTML/PDF/video con URLs absolutas inventadas para practicar reescrituras sin depender de Elsevier/IOP.

---

## 7. Portal de invitados

### URLs

| URL | Quién | Función |
|-----|-------|---------|
| `/guest/` | Público | Formulario de auto-registro |
| `/guest/admin` | Rol `admin` | Aprobar / rechazar pendientes |

### Flujo funcional

1. El invitado completa el formulario → `POST /guest/api/register`
2. Se crea usuario en Keycloak **deshabilitado** con atributo `guest_status=pending` y rol `guest`
3. Si LDAP está configurado, se crea entrada con `employeeType=pending`
4. Un administrador inicia sesión (p. ej. `librarian`) y abre `/guest/admin`
5. **Aprobar** → habilita la cuenta (`guest_status=approved`) y LDAP `employeeType=guest`
6. **Rechazar** → marca rechazo; LDAP `employeeType=rejected`

### Configuración one-time en Keycloak

```bash
./scripts/configure-guest-portal.sh
```

Otorga al service account del cliente `guest-portal` los roles de Admin API necesarios (`manage-users`, `view-users`, etc.) y habilita atributos no gestionados.

### Endpoints de la API (detrás de `/guest/`)

| Método | Ruta | Auth | Uso |
|--------|------|------|-----|
| GET | `/` | Público | Página de registro |
| POST | `/api/register` | Público | Alta pendiente |
| GET | `/admin` | SSO + admin | UI de aprobación |
| GET | `/api/admin/pending` | SSO + admin | Listar pendientes |
| GET | `/api/admin/rejected` | SSO + admin | Listar rechazados |
| POST | `/api/admin/{id}/approve` | SSO + admin | Aprobar |
| POST | `/api/admin/{id}/reject` | SSO + admin | Rechazar |

**Importante:** no se parchea el core de Keycloak; todo el flujo usa Admin API + usuarios deshabilitados.

---

## 8. Federación LDAP

### Objetivo

Los usuarios institucionales de OpenLDAP (`usuarios.bibliolatino.com`) pueden autenticarse en el mismo realm `library` que el proxy.

### Configuración

Variables en `.env` (ver sección 11). Luego:

```bash
./scripts/configure-ldap-federation.sh
```

El script:

1. Ajusta ACLs en el servidor LDAP (vía SSH, según credenciales de despliegue)
2. Crea/actualiza el componente Keycloak `bibliolatino-ldap` (modo WRITABLE, sync periódico)
3. Dispara sincronización completa

### Invitados y LDAP

Si `LDAP_URL` y bind están definidos, el guest-portal **refleja** invitados en la OU de usuarios. Si LDAP no está configurado, el portal sigue funcionando solo con Keycloak.

---

## 9. Analíticas y Metabase

### Pipeline

```
Nginx (library_access.log)
    → volumen nginx_logs
    → log-worker (clasifica content_type)
    → Postgres DB analytics, tabla access_events
    → Metabase (/metabase/)
```

### Esquema (resumen)

Tabla `access_events`: tiempo, IP, método, path, status, bytes, usuario, email, campus, resource, content_type, …

Vistas:

- `v_access_by_day` — hits y usuarios únicos por día / recurso / tipo
- `v_access_by_resource` — agregación por recurso y tipo

Tipos de contenido típicos: `pdf`, `video`, `article`, `asset`, `auth`, `portal`, `other`.

### Primer uso de Metabase

1. Abrir `https://proxy.bibliolatino.com/metabase/`
2. Completar el asistente de instalación (usuario admin de Metabase)
3. **No** conectar un MySQL de ejemplo de la biblioteca: es el wizard de Metabase
4. Añadir base de datos **PostgreSQL**:
   - Host: `postgres` (nombre del servicio Docker; desde fuera del compose usar el host/puerto expuesto si aplica)
   - Base de datos: `analytics`
   - Usuario / contraseña: los mismos de Postgres del `.env` (`POSTGRES_USER` / `POSTGRES_PASSWORD`)
   - Schemas: **Todos** (o al menos `public`)
5. Crear preguntas sobre `access_events` o las vistas
6. Exportar desde cualquier pregunta/dashboard: **CSV, XML, PDF** (función nativa de Metabase)

La base de aplicación de Metabase es el database Postgres `metabase` (creado en el init); no confundir con `analytics` (datos de uso).

---

## 10. Operación diaria (runbooks)

### R1 — Ver estado de contenedores

```bash
docker compose ps
docker compose logs -f nginx keycloak oauth2-proxy guest-portal log-worker --tail=100
```

### R2 — Recargar Nginx tras cambiar stanzas o CIDRs

```bash
./scripts/render-campus-geo.sh   # solo si cambió INSTITUTIONAL_CIDRS
PUBLIC_HOST=proxy.bibliolatino.com PUBLIC_SCHEME=https ./scripts/generate-proxy-conf.py
docker compose exec nginx nginx -s reload
```

### R3 — Aprobar un invitado

1. Entrar con usuario `admin` (p. ej. `librarian`)
2. Ir a `/guest/admin`
3. Aprobar o rechazar

### R4 — Añadir editorial / base de datos

Ver sección 6. Recordar whitelist de IP de egreso.

### R5 — Reiniciar un servicio

```bash
docker compose up -d --build guest-portal
docker compose restart log-worker
```

### R6 — Certificado TLS

```bash
./scripts/issue-tls-cert.sh
```

Renovar según política de Let's Encrypt (cron o repetición del script).

### R7 — Backup recomendado

- Volumen `postgres_data` (Keycloak + analytics + metabase)
- Archivo `.env` (secretos; guardar fuera del repo)
- Carpeta `stanzas/` y `certs/`

```bash
docker compose exec postgres pg_dumpall -U "$POSTGRES_USER" > backup-$(date +%F).sql
```

---

## 11. Variables de entorno

Definidas en `.env` (plantilla: `.env.example`). **No** commitear secretos reales.

| Variable | Propósito |
|----------|-----------|
| `POSTGRES_*` | Credenciales Postgres compartidas |
| `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD` | Admin bootstrap de Keycloak |
| `PUBLIC_HOST` / `PUBLIC_SCHEME` / `APP_URL` | URL pública del proxy |
| `KEYCLOAK_PUBLIC_URL` | URL de Keycloak vista por el navegador |
| `KEYCLOAK_SSL_REQUIRED` | Política SSL del realm |
| `OAUTH2_PROXY_CLIENT_SECRET` | Secreto del cliente `library-proxy` |
| `OAUTH2_PROXY_COOKIE_SECRET` | 16/24/32 bytes (p. ej. `openssl rand -hex 16`) |
| `OAUTH2_PROXY_COOKIE_SECURE` | `true` en HTTPS |
| `INSTITUTIONAL_CIDRS` | CIDRs de campus (bypass SSO) |
| `GUEST_CLIENT_SECRET` | Secreto del cliente `guest-portal` |
| `LDAP_*` | Conexión y binds OpenLDAP |
| `HTTP_PORT` / `HTTPS_PORT` | Puertos publicados de Nginx |
| `CERTBOT_EMAIL` | Email Let's Encrypt |

Credenciales de despliegue remoto (SSH, IPs) pueden vivir en `docs/credentials.env` (gitignored); no forman parte del ejemplo público.

---

## 12. Scripts de utilidad

| Script | Para qué |
|--------|----------|
| `generate-proxy-conf.py` | Genera Nginx locations + `databases.html` |
| `render-campus-geo.sh` | Genera `campus-ip.geo.conf` |
| `configure-public-access.sh` | Ajusta SSL y redirect URIs de Keycloak a `APP_URL` |
| `configure-guest-portal.sh` | Roles Admin API del portal de invitados |
| `configure-ldap-federation.sh` | Federación LDAP en Keycloak + ACLs |
| `issue-tls-cert.sh` | Certificado Let's Encrypt |
| `validate-m1.sh` … `validate-m4.sh` | Smokes por hito |
| `validate-auth-flows.sh` | Redirects, logout, HTTP→HTTPS |
| `init-analytics-db.sql` | Crea DB `analytics` y `metabase` |
| `analytics-schema.sql` | DDL de eventos (espejo del worker) |
| `deploy_m4.py` / `check_m4.py` | Despliegue/chequeo remoto M4 |

---

## 13. Validación por hitos

```bash
./scripts/validate-m1.sh          # health, OIDC, redirects
./scripts/validate-auth-flows.sh  # logout, HTTPS, rutas públicas
./scripts/validate-m2.sh          # databases + /r/* protegidos
./scripts/validate-m3.sh          # guest público + admin gated
./scripts/validate-m4.sh          # metabase, analytics, log-worker
```

Interpretación: salida 0 = smoke OK. Si falla, revisar `docker compose logs` del servicio indicado.

---

## 14. Solución de problemas

| Síntoma | Causas probables | Qué hacer |
|---------|------------------|-----------|
| Loop de login / redirect | `APP_URL` / redirect URIs desalineados | `./scripts/configure-public-access.sh`; revisar secretos oauth2 |
| 502 en `/r/...` | Upstream caído o stanza mal generado | `docker compose ps`; regenerar conf; logs nginx |
| ScienceDirect/Scopus/IOP no cargan | IP no whitelisteada | Confirmar `169.58.217.137` con la editorial; probar `/r/simulator/` |
| Campus no omite SSO | CIDRs vacíos o geo no regenerado | Set `INSTITUTIONAL_CIDRS` + `render-campus-geo.sh` + reload |
| `/guest/admin` vacío o 403 | Usuario sin rol `admin`; script guest no corrido | Usar `librarian`; `configure-guest-portal.sh` |
| Invitado no puede entrar tras aprobar | Usuario aún disabled; cache | Verificar en Keycloak Users que esté Enabled |
| Metabase pide MySQL / datos de ejemplo | Es el wizard genérico | Cerrar tarjeta; elegir **PostgreSQL** → DB `analytics` |
| Metabase: password rejected | Credencial distinta a Postgres real | Usar `POSTGRES_USER`/`PASSWORD` del `.env` del servidor |
| Sin filas en analytics | log-worker parado o log vacío | `docker compose logs log-worker`; generar tráfico autenticado |
| LDAP no autentica | Federación no creada / bind incorrecto | Re-ejecutar `configure-ldap-federation.sh`; sync en Keycloak Admin |

---

## 15. Capacitación — módulos y ejercicios

Objetivo: que el equipo in-house pueda **operar, explicar y extender** el sistema sin depender del proveedor.

Modalidad: exposición apoyada en demostración sobre el sistema, ejercicios prácticos y esta
documentación como material de consulta. El módulo E está dirigido al equipo técnico y puede
omitirse con audiencia no técnica.

### Módulo A — Visión y arquitectura

**Explicar**

- Problema que resuelve (acceso remoto unificado vs EZproxy comercial)
- Diagrama de flujo (sección 2)
- Qué hace cada contenedor

**Ejercicio A1**

1. Abrir `/healthz` y confirmar 200
2. Listar contenedores con `docker compose ps`
3. Identificar en la salida: nginx, keycloak, oauth2-proxy, guest-portal, metabase, log-worker

**Criterio de éxito:** el asistente nombra qué servicio atiende SSO, invitados y analíticas.

---

### Módulo B — SSO y roles

**Explicar**

- Login remoto vs bypass de campus
- Roles `user` / `admin` / `guest`
- Dónde se administran usuarios (Keycloak `/admin/`)

**Ejercicio B1 — Usuario estándar**

1. Cerrar sesión si hay cookie previa
2. Abrir `/databases.html` con `demo` / `demo123`
3. Confirmar acceso al catálogo
4. Abrir `/guest/admin` → debe denegar o no mostrar funciones de admin

**Ejercicio B2 — Administrador**

1. Entrar como `librarian` / `admin123`
2. Abrir `/guest/admin` con éxito
3. Abrir Keycloak Admin y localizar realm `library` y roles

**Criterio de éxito:** diferencia clara entre usuario de biblioteca y administrador.

---

### Módulo C — Proxy de editoriales

**Explicar**

- Catálogo `databases.html`
- Stanzas YAML y regeneración
- Por qué existe el simulador
- Whitelist de IP de egreso

**Ejercicio C1 — Simulador**

1. Tras SSO, abrir `/r/simulator/`
2. Navegar un artículo HTML, un PDF y (si hay) video
3. Observar que la barra de direcciones sigue en `proxy.bibliolatino.com`

**Ejercicio C2 — Añadir stanza de prueba** (solo en entorno de laboratorio)

1. Copiar `stanzas/simulator.yml` a `stanzas/demo2.yml`
2. Cambiar `name`/`title`
3. Regenerar conf y reload nginx
4. Verificar que aparece en el catálogo

**Criterio de éxito:** el asistente explica qué archivo tocar para una base nueva y qué comando regenera Nginx.

---

### Módulo D — Invitados

**Explicar**

- Auto-registro sin tocar el core de Keycloak
- Estados pending / approved / rejected
- Relación opcional con LDAP

**Ejercicio D1 — Ciclo completo**

1. En ventana privada, registrar un invitado de prueba en `/guest/`
2. Con `librarian`, abrir `/guest/admin` y ver el pendiente
3. Aprobar
4. Intentar login del invitado en el proxy
5. (Opcional) Rechazar otro registro de prueba y comprobar que no entra

**Criterio de éxito:** completar registro → aprobación → login sin ayuda.

---

### Módulo E — LDAP

**Explicar**

- User federation en Keycloak
- Script `configure-ldap-federation.sh`
- Sync periódico vs sync manual

**Ejercicio E1**

1. En Keycloak Admin → User federation → verificar `bibliolatino-ldap` (si está desplegado)
2. Buscar un usuario LDAP conocido
3. Probar login con ese usuario (credenciales institucionales)

**Criterio de éxito:** el técnico sabe dónde mirar si “LDAP no autentica”.

---

### Módulo F — Analíticas / Metabase

**Explicar**

- De dónde salen los datos (access log → worker → Postgres)
- Diferencia entre DB `analytics` y DB `metabase`
- Exportaciones CSV / XML / PDF

**Ejercicio F1**

1. Generar tráfico: login + visita a `/r/simulator/` (HTML y PDF)
2. Abrir `/metabase/`
3. Explorar tabla `access_events` o vista `v_access_by_resource`
4. Crear una pregunta simple (p. ej. hits por `content_type`)
5. Exportar a CSV y a PDF

**Criterio de éxito:** el bibliotecario obtiene un export sin intervención de desarrollo.

---

### Módulo G — Operación y contingencias

**Explicar**

- Runbooks R1–R7
- Validadores `validate-m*.sh`
- Tabla de troubleshooting (sección 14)

**Ejercicio G1**

1. Ejecutar `./scripts/validate-m3.sh` y `./scripts/validate-m4.sh`
2. Simular (en lab) `docker compose restart nginx` y verificar recuperación
3. Localizar logs de un error con `docker compose logs nginx --tail=50`

**Criterio de éxito:** el operador reinicia un servicio y confirma salud con `/healthz`.

---

### Guía del instructor

**Preparación del entorno de prácticas:**

- [ ] Stack `docker compose up -d` saludable
- [ ] Cuentas demo válidas (o cuentas reales de prueba)
- [ ] Simulador accesible
- [ ] Al menos un invitado de prueba limpio para el ejercicio D
- [ ] Metabase con Postgres `analytics` ya conectado
- [ ] Entorno de laboratorio separado para los ejercicios que modifican configuración (C2, G1)

**Conducción:**

- [ ] Recorrer los módulos A→G (omitir E si la audiencia no es técnica)
- [ ] Realizar cada ejercicio sobre el sistema, no solo como demostración
- [ ] Reservar espacio para preguntas en los módulos con impacto operativo (C, D, F)

**Cierre y materiales:**

- [ ] Entregar el manual y la presentación de apoyo
- [ ] Entregar lista de secretos rotados / pendientes de rotar
- [ ] Confirmar IP de egreso con editores (si aún no)

### Preguntas frecuentes para la capacitación

**¿Por qué no usamos el registro nativo de Keycloak para invitados?**  
Porque se requiere aprobación manual y usuarios deshabilitados hasta el OK del bibliotecario, sin alterar el core del IdP.

**¿El personal del campus necesita VPN?**  
No necesariamente: desde IPs institucionales puede haber bypass; desde fuera usa SSO.

**¿Podemos añadir JSTOR / otra base?**  
Sí: nuevo YAML en `stanzas/`, regenerar, reload, y whitelist de IP si el editor lo exige.

**¿Dónde se cambian contraseñas de demo?**  
Keycloak Admin → Users; además rotar secretos en `.env` y reiniciar servicios afectados.

---

## 16. Anexo: URLs, cuentas y checklist de entrega

### URLs de producción (bibliolatino)

| URL | Uso |
|-----|-----|
| https://proxy.bibliolatino.com/ | Inicio / SSO |
| https://proxy.bibliolatino.com/databases.html | Catálogo de bases |
| https://proxy.bibliolatino.com/r/simulator/ | Demo de reescritura |
| https://proxy.bibliolatino.com/r/sciencedirect/ | ScienceDirect |
| https://proxy.bibliolatino.com/r/scopus/ | Scopus |
| https://proxy.bibliolatino.com/r/iop/ | IOP |
| https://proxy.bibliolatino.com/guest/ | Registro invitados |
| https://proxy.bibliolatino.com/guest/admin | Aprobación |
| https://proxy.bibliolatino.com/admin/ | Keycloak Admin |
| https://proxy.bibliolatino.com/metabase/ | Analíticas |
| https://proxy.bibliolatino.com/healthz | Health check |

### Checklist de entrega (handover)

- [ ] Código fuente del repositorio
- [ ] `docker-compose.yml` + imágenes / builds
- [ ] `.env.example` actualizado (sin secretos reales en git)
- [ ] Este manual, en texto (`docs/manual-y-capacitacion.md`) y en Word (`docs/Manual-Tecnico-Operativo-y-Capacitacion.docx`)
- [ ] Nota de autenticaciones adicionales (`docs/milestone2-auth-and-stanzas.md`)
- [ ] Scripts de validación M1–M4 en verde (o incidencias documentadas)
- [ ] Metabase conectado a `analytics` con al menos una pregunta de ejemplo
- [ ] Presentación de capacitación entregada (`docs/Capacitacion-University-Library-Proxy.pptx`)
- [ ] IP de egreso comunicada a editores
- [ ] Contraseñas/secretos de demo rotados o plan de rotación acordado

### Documentos relacionados en el repo

| Archivo | Contenido |
|---------|-----------|
| `README.md` | Arranque rápido y resumen de hitos |
| `docs/manual-y-capacitacion.md` | **Este documento** (manual + capacitación) |
| `docs/Manual-Tecnico-Operativo-y-Capacitacion.docx` | Manual completo en formato Word, para entrega al cliente |
| `docs/Capacitacion-University-Library-Proxy.pptx` | Presentación de apoyo a la capacitación (31 láminas) |
| `docs/milestone2-auth-and-stanzas.md` | SAML / CAS / LTI / LDAP / stanzas |
| `docs/detail.md` | Alcance original del encargo |
| `.env.example` | Plantilla de configuración |

---

*Fin del manual. Para dudas operativas usar primero la sección 14 (troubleshooting) y los validadores de la sección 13.*
