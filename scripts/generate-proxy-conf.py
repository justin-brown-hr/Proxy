#!/usr/bin/env python3
"""Generate nginx resource proxy config from stanzas/*.yml (EZproxy-style)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
STANZA_DIR = ROOT / "stanzas"
OUT = ROOT / "nginx" / "resources.locations.conf"
PORTAL = ROOT / "test-resource" / "html" / "databases.html"

PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "localhost")
PUBLIC_SCHEME = os.environ.get("PUBLIC_SCHEME", "https")


def load_stanzas() -> list[dict]:
    items = []
    for path in sorted(STANZA_DIR.glob("*.yml")):
        data = yaml.safe_load(path.read_text()) or {}
        if not data.get("enabled", True):
            continue
        if "name" not in data or "target" not in data:
            raise SystemExit(f"Invalid stanza {path}: need name + target")
        items.append(data)
    return items


def nginx_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render_resource(stanza: dict) -> str:
    name = stanza["name"]
    target = stanza["target"].rstrip("/")
    host_header = stanza.get("host_header") or target.split("://", 1)[-1].split("/", 1)[0]
    start = stanza.get("start_path", "/")
    if not start.startswith("/"):
        start = "/" + start
    proxy_base = f"{PUBLIC_SCHEME}://{PUBLIC_HOST}/r/{name}"
    ssl = target.startswith("https://")

    lines = [
        f"# --- {stanza.get('title', name)} ({name}) ---",
        f"location = /r/{name} {{",
        f"    return 302 /r/{name}{start if start != '/' else '/'};",
        "}",
        f"location /r/{name}/ {{",
        "    auth_request /auth-gate;",
        "    auth_request_set $auth_user  $upstream_http_x_auth_request_user;",
        "    auth_request_set $auth_email $upstream_http_x_auth_request_email;",
        "    error_page 401 = @error401;",
        "",
        f"    rewrite ^/r/{name}/(.*)$ /$1 break;",
        f"    proxy_pass {target};",
        "    proxy_http_version 1.1;",
        f"    proxy_set_header Host {host_header};",
        "    proxy_set_header X-Real-IP $remote_addr;",
        "    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "    proxy_set_header X-Forwarded-Proto https;",
        "    proxy_set_header Accept-Encoding \"\";",
        "    proxy_set_header X-Auth-Request-User $auth_user;",
        "    proxy_set_header X-Auth-Request-Email $auth_email;",
        "    proxy_buffering on;",
        "    proxy_buffer_size 128k;",
        "    proxy_buffers 8 256k;",
        "    proxy_busy_buffers_size 256k;",
        "    proxy_read_timeout 120s;",
        "    proxy_redirect off;",
    ]
    if ssl:
        lines.append("    proxy_ssl_server_name on;")
        lines.append(f"    proxy_ssl_name {host_header};")

    lines += [
        "",
        "    # Keep users inside the proxy for absolute publisher URLs",
        "    sub_filter_once off;",
        "    sub_filter_types text/css application/javascript application/json;",
    ]

    for pair in stanza.get("find_replace") or []:
        find = nginx_escape(pair["find"])
        replace = nginx_escape(pair["replace"].replace("{{PROXY_BASE}}", proxy_base))
        lines.append(f'    sub_filter "{find}" "{replace}";')

    lines.append("}")
    lines.append("")

    for extra in stanza.get("extra_upstreams") or []:
        prefix = extra["path_prefix"].rstrip("/")
        etarget = extra["target"].rstrip("/")
        ehost = extra.get("host_header") or etarget.split("://", 1)[-1].split("/", 1)[0]
        essl = etarget.startswith("https://")
        lines += [
            f"location /r/{name}{prefix}/ {{",
            "    auth_request /auth-gate;",
            "    error_page 401 = @error401;",
            f"    rewrite ^/r/{name}{prefix}/(.*)$ /$1 break;",
            f"    proxy_pass {etarget};",
            f"    proxy_set_header Host {ehost};",
            "    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "    proxy_set_header Accept-Encoding \"\";",
        ]
        if essl:
            lines.append("    proxy_ssl_server_name on;")
            lines.append(f"    proxy_ssl_name {ehost};")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def render_portal(stanzas: list[dict]) -> str:
    # Prefer live resources first, demo last
    ordered = sorted(stanzas, key=lambda s: (0 if s.get("mode") != "simulator" else 1, s.get("title", "")))
    items = []
    for s in ordered:
        desc = s.get("description") or "Recurso académico institucional."
        title = s.get("title", s["name"])
        initial = (title[:1] or "R").upper()
        items.append(
            f"""      <a class="resource" href="/r/{s['name']}/" target="_blank" rel="noopener noreferrer">
        <span class="resource-icon" aria-hidden="true">{initial}</span>
        <div>
          <h2>{title}</h2>
          <p>{desc}</p>
        </div>
        <span class="go">Abrir →</span>
      </a>"""
        )
    items_html = "\n".join(items)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bibliolatino — Bases de datos</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;600;700&family=Fraunces:opsz,wght@9..144,500;9..144,650&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/assets/portal.css" />
</head>
<body>
  <div class="utility">
    <div class="utility-inner">
      <span>Portal institucional de acceso remoto a recursos electrónicos</span>
      <div class="utility-links">
        <a href="/">Inicio</a>
        <a href="mailto:biblioteca@bibliolatino.com">Soporte biblioteca</a>
      </div>
    </div>
  </div>

  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="/">
        <span class="brand-mark" aria-hidden="true">B</span>
        <span class="brand-text">
          <span class="brand-name">Bibliolatino</span>
          <span class="brand-tag">Biblioteca digital · acceso remoto seguro</span>
        </span>
      </a>
      <nav class="header-nav" aria-label="Principal">
        <a href="/">Inicio</a>
        <a class="is-active" href="/databases.html">Bases de datos</a>
        <a href="/guest/admin">Invitados</a>
        <a class="cta" href="/logout">Cerrar sesión</a>
        <div class="user-chip" id="user-chip">
          <span class="user-avatar" id="chip-avatar">U</span>
          <span id="chip-name">Sesión</span>
        </div>
      </nav>
    </div>
  </header>

  <div class="shell">
    <main class="panel">
      <p class="eyebrow">Catálogo</p>
      <h1>Bases de datos y revistas</h1>
      <p class="lead">
        Selecciona un recurso para buscar artículos, citas o publicaciones.
        Cada recurso se abre en una nueva pestaña con tu sesión institucional.
      </p>
      <div class="catalog">
{items_html}
      </div>
      <p class="note">
        Si un recurso no muestra el texto completo, la editorial puede estar aún
        habilitando la dirección IP del servidor de acceso remoto de la institución.
      </p>
    </main>
  </div>

  <footer class="site-footer">
    <div class="footer-inner">
      <div class="footer-brand">
        <p class="name">Bibliolatino</p>
        <p>Plataforma de acceso remoto a recursos académicos electrónicos para instituciones de educación superior.</p>
      </div>
      <div class="footer-col">
        <h3>Servicios</h3>
        <a href="/databases.html">Bases de datos</a>
        <a href="/">Portal de acceso</a>
        <span>Revistas y e-books</span>
      </div>
      <div class="footer-col">
        <h3>Soporte</h3>
        <a href="mailto:biblioteca@bibliolatino.com">Contacto biblioteca</a>
        <span>Horario de atención: lun–vie</span>
        <span>Acceso con cuenta institucional</span>
      </div>
      <div class="footer-col">
        <h3>Institución</h3>
        <span>Acceso federado / SSO</span>
        <span>proxy.bibliolatino.com</span>
        <a href="/logout">Cerrar sesión</a>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© Bibliolatino · Acceso institucional seguro</span>
      <span>Uso exclusivo para miembros autorizados</span>
    </div>
  </footer>

  <script src="/assets/portal.js"></script>
</body>
</html>
"""


def main() -> None:
    stanzas = load_stanzas()
    header = (
        "# AUTO-GENERATED by scripts/generate-proxy-conf.py — do not edit by hand\n"
        f"# Public base: {PUBLIC_SCHEME}://{PUBLIC_HOST}/r/<name>/\n"
        f"# Stanzas: {', '.join(s['name'] for s in stanzas)}\n\n"
    )
    body = "\n".join(render_resource(s) for s in stanzas)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(header + body)
    PORTAL.parent.mkdir(parents=True, exist_ok=True)
    PORTAL.write_text(render_portal(stanzas))
    print(f"Wrote {OUT}")
    print(f"Wrote {PORTAL}")
    print(f"Resources: {', '.join(s['name'] for s in stanzas)}")


if __name__ == "__main__":
    main()
