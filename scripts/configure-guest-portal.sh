#!/usr/bin/env bash
# Ensure guest-portal service account can manage users (Keycloak Admin API).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.env"

KC="http://127.0.0.1:${KEYCLOAK_PORT:-8080}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

echo "Waiting for Keycloak..."
for i in $(seq 1 60); do
  curl -fsS "$KC/realms/master" >/dev/null 2>&1 && break
  sleep 2
done

TOKEN=$(curl -fsS \
  -d "client_id=admin-cli" \
  -d "username=${ADMIN_USER}" \
  -d "password=${ADMIN_PASS}" \
  -d "grant_type=password" \
  "$KC/realms/master/protocol/openid-connect/token" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

AUTH=( -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" )

python3 - "$TOKEN" "$KC" <<'PY'
import json, sys, urllib.request

token, kc = sys.argv[1:3]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def req(url, method="GET", data=None):
    body = None if data is None else json.dumps(data).encode()
    r = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(r) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None

# Find guest-portal client
clients = req(f"{kc}/admin/realms/library/clients?clientId=guest-portal")
if not clients:
    print("guest-portal client missing — import realm or create client")
    sys.exit(1)
cid = clients[0]["id"]

# Service account user
sa = req(f"{kc}/admin/realms/library/clients/{cid}/service-account-user")
sa_id = sa["id"]

# realm-management client
rm = req(f"{kc}/admin/realms/library/clients?clientId=realm-management")[0]
rm_id = rm["id"]

# Available client roles
roles = req(f"{kc}/admin/realms/library/clients/{rm_id}/roles")
wanted = {"manage-users", "view-users", "query-users", "view-realm"}
to_add = [r for r in roles if r["name"] in wanted]

# Current mappings
current = req(f"{kc}/admin/realms/library/users/{sa_id}/role-mappings/clients/{rm_id}") or []
have = {r["name"] for r in current}
missing = [r for r in to_add if r["name"] not in have]
if missing:
    req(
        f"{kc}/admin/realms/library/users/{sa_id}/role-mappings/clients/{rm_id}",
        method="POST",
        data=missing,
    )
    print("Assigned roles:", ", ".join(sorted(r["name"] for r in missing)))
else:
    print("Service account already has required roles")

# Ensure guest realm role exists
realm_roles = req(f"{kc}/admin/realms/library/roles")
if not any(r["name"] == "guest" for r in realm_roles):
    req(f"{kc}/admin/realms/library/roles", method="POST", data={"name": "guest", "description": "Approved guest"})
    print("Created realm role: guest")
else:
    print("Realm role guest OK")

# Keycloak 24+ user profiles: allow guest_* attributes via Admin API
try:
    profile = req(f"{kc}/admin/realms/library/users/profile")
    if profile.get("unmanagedAttributePolicy") != "ENABLED":
        profile["unmanagedAttributePolicy"] = "ENABLED"
        req(f"{kc}/admin/realms/library/users/profile", method="PUT", data=profile)
        print("Enabled unmanaged user attributes")
    else:
        print("Unmanaged user attributes already ENABLED")
except Exception as exc:  # noqa: BLE001
    print("Warning: could not update user profile policy:", exc)

print("Guest portal Keycloak setup done.")
PY
