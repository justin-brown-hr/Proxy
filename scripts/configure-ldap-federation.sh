#!/usr/bin/env bash
# Configure OpenLDAP ACLs (keycloak bind can manage users) + Keycloak LDAP federation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
[[ -f "$ROOT/docs/credentials.env" ]] && set -a && source "$ROOT/docs/credentials.env" && set +a
# shellcheck disable=SC1091
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a

LDAP_HOST="${LDAP_SERVER_IP:-169.58.217.129}"
LDAP_URL="${LDAP_URL:-ldap://${LDAP_HOST}:389}"
BASE_DN="${LDAP_BASE_DN:-dc=usuarios,dc=bibliolatino,dc=com}"
ADMIN_DN="${LDAP_BIND_DN:-cn=admin,${BASE_DN}}"
ADMIN_PW="${LDAP_BIND_PASSWORD:?Set LDAP_BIND_PASSWORD in docs/credentials.env}"
KC_BIND_DN="${LDAP_KC_BIND_DN:-uid=keycloak,ou=services,${BASE_DN}}"
KC_BIND_PW="${LDAP_KC_BIND_PASSWORD:?Set LDAP_KC_BIND_PASSWORD in docs/credentials.env}"
USERS_OU="${LDAP_USERS_OU:-ou=usuarios,${BASE_DN}}"

KC="${KEYCLOAK_INTERNAL_URL:-http://127.0.0.1:${KEYCLOAK_PORT:-8080}}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

echo "==> Waiting for Keycloak at $KC ..."
for _ in $(seq 1 60); do
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

export TOKEN KC LDAP_URL BASE_DN ADMIN_DN ADMIN_PW KC_BIND_DN KC_BIND_PW USERS_OU \
  LDAP_SERVER_IP LDAP_SERVER_USER LDAP_SERVER_PASS

python3 <<'PY'
import json, os, sys, time, urllib.request
import paramiko

token = os.environ["TOKEN"]
kc = os.environ["KC"].rstrip("/")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def req(url, method="GET", data=None):
    body = None if data is None else json.dumps(data).encode()
    r = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        print(f"HTTP {e.code} {method} {url}\n{raw[:500]}", file=sys.stderr)
        raise

# --- LDAP ACL via SSH so keycloak bind can write users ---
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    os.environ["LDAP_SERVER_IP"],
    username=os.environ["LDAP_SERVER_USER"],
    password=os.environ["LDAP_SERVER_PASS"],
    timeout=30,
    allow_agent=False,
    look_for_keys=False,
)
kc_bind = os.environ["KC_BIND_DN"]
users_ou = os.environ["USERS_OU"]
base_dn = os.environ["BASE_DN"]
admin_dn = os.environ["ADMIN_DN"]
admin_pw = os.environ["ADMIN_PW"]

# Read current access
stdin, stdout, stderr = ssh.exec_command(
    "ldapsearch -Y EXTERNAL -H ldapi:/// -b 'olcDatabase={1}mdb,cn=config' olcAccess 2>/dev/null"
)
print(stdout.read().decode())

ldif = f"""dn: olcDatabase={{1}}mdb,cn=config
changetype: modify
replace: olcAccess
olcAccess: {{0}}to attrs=userPassword,shadowLastChange by self write by dn.exact="{kc_bind}" write by anonymous auth by * none
olcAccess: {{1}}to dn.subtree="{users_ou}" by dn.exact="{kc_bind}" write by self write by users read by * none
olcAccess: {{2}}to dn.subtree="ou=grupos,{base_dn}" by dn.exact="{kc_bind}" write by users read by * none
olcAccess: {{3}}to * by dn.exact="{kc_bind}" read by self write by users read by * none
"""
sftp = ssh.open_sftp()
with sftp.file("/tmp/kc_acl.ldif", "w") as f:
    f.write(ldif)
sftp.close()
stdin, stdout, stderr = ssh.exec_command("ldapmodify -Y EXTERNAL -H ldapi:/// -f /tmp/kc_acl.ldif 2>&1")
print(stdout.read().decode() + stderr.read().decode())

# Verify keycloak bind can search
cmd = (
    f"ldapsearch -x -H ldap://127.0.0.1:389 -D '{kc_bind}' -w '{os.environ['KC_BIND_PW']}' "
    f"-b '{users_ou}' '(objectClass=inetOrgPerson)' uid 2>&1 | tail -15"
)
stdin, stdout, stderr = ssh.exec_command(cmd)
print("KC bind search:", stdout.read().decode() + stderr.read().decode())
ssh.close()

# --- Keycloak LDAP user federation component ---
status, comps = req(f"{kc}/admin/realms/library/components?type=org.keycloak.storage.UserStorageProvider")
existing = [c for c in (comps or []) if c.get("name") == "bibliolatino-ldap"]
parent_id = None
# realm id
_, realm = req(f"{kc}/admin/realms/library")
# components need parentId = realm id
_, realms = req(f"{kc}/admin/realms")
realm_id = next(r["id"] for r in realms if r["realm"] == "library")

config = {
    "enabled": ["true"],
    "priority": ["0"],
    "fullSyncPeriod": ["86400"],
    "changedSyncPeriod": ["300"],
    "cachePolicy": ["DEFAULT"],
    "evictionDay": [],
    "evictionHour": [],
    "evictionMinute": [],
    "maxLifespan": [],
    "batchSizeForSync": ["1000"],
    "editMode": ["WRITABLE"],
    "syncRegistrations": ["true"],
    "vendor": ["other"],
    "usernameLDAPAttribute": ["uid"],
    "rdnLDAPAttribute": ["uid"],
    "uuidLDAPAttribute": ["entryUUID"],
    "userObjectClasses": ["inetOrgPerson, posixAccount"],
    "connectionUrl": [os.environ["LDAP_URL"]],
    "usersDn": [users_ou],
    "authType": ["simple"],
    "bindDn": [os.environ["KC_BIND_DN"]],
    "bindCredential": [os.environ["KC_BIND_PW"]],
    "customUserSearchFilter": [],
    "searchScope": ["1"],
    "validatePasswordPolicy": ["false"],
    "trustEmail": ["true"],
    "useTruststoreSpi": ["ldapsOnly"],
    "connectionPooling": ["true"],
    "connectionTimeout": ["10000"],
    "readTimeout": ["10000"],
    "pagination": ["true"],
    "allowKerberosAuthentication": ["false"],
    "debug": ["false"],
    "useKerberosForPasswordAuthentication": ["false"],
    "startTls": ["false"],
}

payload = {
    "name": "bibliolatino-ldap",
    "providerId": "ldap",
    "providerType": "org.keycloak.storage.UserStorageProvider",
    "parentId": realm_id,
    "config": config,
}

if existing:
    cid = existing[0]["id"]
    # merge id for update
    payload["id"] = cid
    req(f"{kc}/admin/realms/library/components/{cid}", method="PUT", data=payload)
    print(f"Updated LDAP federation component {cid}")
else:
    req(f"{kc}/admin/realms/library/components", method="POST", data=payload)
    status, comps = req(f"{kc}/admin/realms/library/components?type=org.keycloak.storage.UserStorageProvider")
    existing = [c for c in (comps or []) if c.get("name") == "bibliolatino-ldap"]
    cid = existing[0]["id"] if existing else None
    print(f"Created LDAP federation component {cid}")

if not cid:
    sys.exit("LDAP component missing after create")

# Mapper: username, email, first name, last name usually auto-created; ensure email
_, mappers = req(f"{kc}/admin/realms/library/components?parent={cid}")
mapper_names = {m.get("name") for m in (mappers or [])}
wanted_mappers = [
    ("email", "email", "mail", "user-attribute-ldap-mapper"),
    ("first name", "firstName", "cn", "user-attribute-ldap-mapper"),  # may conflict; use givenName if present
    ("last name", "lastName", "sn", "user-attribute-ldap-mapper"),
    ("username", "username", "uid", "user-attribute-ldap-mapper"),
]
# Prefer givenName for firstName if we add attribute later; OpenLDAP sample uses cn as full name
# Keep default mappers Keycloak creates; trigger sync instead.

# Sync all users
try:
    req(
        f"{kc}/admin/realms/library/user-storage/{cid}/sync?action=triggerFullSync",
        method="POST",
        data={},
    )
    print("Triggered full LDAP sync")
except Exception as exc:
    print("Sync trigger note:", exc)

time.sleep(2)
_, users = req(f"{kc}/admin/realms/library/users?max=50")
print(f"Keycloak users visible after sync: {len(users or [])}")
for u in (users or [])[:10]:
    print(" -", u.get("username"), u.get("email"), "fed=", u.get("federationLink") is not None)

print("LDAP federation setup done.")
PY
