#!/usr/bin/env bash
# Patch live Keycloak realm for public domain access (import only runs on first boot).
# Admin API is always called via localhost.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.env"

APP_URL="${APP_URL:-http://localhost}"
KC_ADMIN_URL="http://127.0.0.1:${KEYCLOAK_PORT:-8080}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
SSL_REQUIRED="${KEYCLOAK_SSL_REQUIRED:-external}"

echo "Waiting for Keycloak admin at ${KC_ADMIN_URL} ..."
for i in $(seq 1 60); do
  if curl -fsS "${KC_ADMIN_URL}/realms/master" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

TOKEN=$(curl -fsS \
  -d "client_id=admin-cli" \
  -d "username=${ADMIN_USER}" \
  -d "password=${ADMIN_PASS}" \
  -d "grant_type=password" \
  "${KC_ADMIN_URL}/realms/master/protocol/openid-connect/token" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Setting sslRequired=${SSL_REQUIRED} on master and library ..."
for realm in master library; do
  curl -fsS -X PUT \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"sslRequired\":\"${SSL_REQUIRED}\"}" \
    "${KC_ADMIN_URL}/admin/realms/${realm}" >/dev/null
done

python3 - "$TOKEN" "$APP_URL" "$KC_ADMIN_URL" <<'PY'
import json, sys, urllib.request

token, app_url, kc_url = sys.argv[1:4]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Always register both http and https variants for the host
hosts = {app_url}
if app_url.startswith("https://"):
    hosts.add("http://" + app_url[len("https://"):])
elif app_url.startswith("http://"):
    hosts.add("https://" + app_url[len("http://"):])

req = urllib.request.Request(
    f"{kc_url}/admin/realms/library/clients?clientId=library-proxy",
    headers=headers,
)
with urllib.request.urlopen(req) as resp:
    client = json.load(resp)[0]

cid = client["id"]
redirects = set(client.get("redirectUris") or [])
origins = set(client.get("webOrigins") or [])
attrs = client.get("attributes") or {}
logout_uris = set(filter(None, (attrs.get("post.logout.redirect.uris") or "").replace("##", "\n").split("\n")))
for h in hosts:
    redirects.update({f"{h}/*", f"{h}/oauth2/callback"})
    origins.add(h)
    logout_uris.update({h, f"{h}/", f"{h}/*"})
redirects.update({
    "http://localhost/*",
    "http://localhost/oauth2/callback",
    "http://127.0.0.1/*",
    "http://127.0.0.1/oauth2/callback",
})
origins.update({"http://localhost", "http://127.0.0.1", "+"})
client["redirectUris"] = sorted(redirects)
client["webOrigins"] = sorted(origins)
attrs["post.logout.redirect.uris"] = "##".join(sorted(logout_uris))
client["attributes"] = attrs

data = json.dumps(client).encode()
put = urllib.request.Request(
    f"{kc_url}/admin/realms/library/clients/{cid}",
    data=data,
    method="PUT",
    headers=headers,
)
with urllib.request.urlopen(put) as resp:
    resp.read()
print(f"Client redirect URIs updated for {sorted(hosts)}")
print(f"Post-logout redirect URIs: {attrs.get('post.logout.redirect.uris')}")
PY

echo "Done. Public test URL: ${APP_URL}/"
