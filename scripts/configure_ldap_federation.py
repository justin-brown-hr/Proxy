#!/usr/bin/env python3
"""Configure OpenLDAP ACLs + Keycloak LDAP user federation (Milestone 4)."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def http(url: str, token: str, method: str = "GET", data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {url}\n{raw[:800]}") from e


def main() -> None:
    creds = load_env(ROOT / "docs" / "credentials.env")
    dotenv = load_env(ROOT / ".env")
    env = {**dotenv, **creds}

    ldap_ip = env["LDAP_SERVER_IP"]
    base_dn = env.get("LDAP_BASE_DN", "dc=usuarios,dc=bibliolatino,dc=com")
    users_ou = env.get("LDAP_USERS_OU", f"ou=usuarios,{base_dn}")
    kc_bind = env.get("LDAP_KC_BIND_DN", f"uid=keycloak,ou=services,{base_dn}")
    kc_pw = env["LDAP_KC_BIND_PASSWORD"]
    ldap_url = env.get("LDAP_URL", f"ldap://{ldap_ip}:389")

    # --- ACL on LDAP host ---
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        ldap_ip,
        username=env["LDAP_SERVER_USER"],
        password=env["LDAP_SERVER_PASS"],
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
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
    stdin, stdout, stderr = ssh.exec_command(
        "ldapmodify -Y EXTERNAL -H ldapi:/// -f /tmp/kc_acl.ldif 2>&1"
    )
    print("ACL:", stdout.read().decode() + stderr.read().decode())
    ssh.close()

    # --- Keycloak via proxy SSH tunnel to localhost:8080 ---
    proxy = paramiko.SSHClient()
    proxy.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    proxy.connect(
        env["PROXY_IP"],
        username=env["PROXY_USER"],
        password=env["PROXY_PASS"],
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )

    # Use Keycloak admin creds from the proxy host .env (not local defaults)
    stdin, stdout, stderr = proxy.exec_command(
        r"""
set -a; source /opt/library-proxy/.env; set +a
curl -fsS -d client_id=admin-cli -d "username=${KEYCLOAK_ADMIN}" \
  -d "password=${KEYCLOAK_ADMIN_PASSWORD}" -d grant_type=password \
  http://127.0.0.1:8080/realms/master/protocol/openid-connect/token
""",
        timeout=60,
    )
    raw = stdout.read().decode()
    err = stderr.read().decode()
    if not raw:
        raise RuntimeError(f"Keycloak token failed: {err}")
    token = json.loads(raw)["access_token"]

    # Run Keycloak API calls from proxy (has localhost:8080)
    script = f"""
import json, urllib.request, urllib.error, sys
token = '''{token}'''
kc = 'http://127.0.0.1:8080'
ldap_url = '''{ldap_url}'''
users_ou = '''{users_ou}'''
kc_bind = '''{kc_bind}'''
kc_pw = '''{kc_pw}'''

def req(url, method='GET', data=None):
    body = None if data is None else json.dumps(data).encode()
    r = urllib.request.Request(url, data=body, method=method, headers={{
        'Authorization': f'Bearer {{token}}', 'Content-Type': 'application/json'
    }})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        print(e.read().decode()[:800], file=sys.stderr)
        raise

_, realms = req(f'{{kc}}/admin/realms')
realm_id = next(r['id'] for r in realms if r['realm']=='library')
_, comps = req(f'{{kc}}/admin/realms/library/components?type=org.keycloak.storage.UserStorageProvider')
existing = [c for c in (comps or []) if c.get('name')=='bibliolatino-ldap']

config = {{
  'enabled': ['true'],
  'priority': ['0'],
  'fullSyncPeriod': ['86400'],
  'changedSyncPeriod': ['300'],
  'cachePolicy': ['DEFAULT'],
  'batchSizeForSync': ['1000'],
  'editMode': ['WRITABLE'],
  'syncRegistrations': ['true'],
  'vendor': ['other'],
  'usernameLDAPAttribute': ['uid'],
  'rdnLDAPAttribute': ['uid'],
  'uuidLDAPAttribute': ['entryUUID'],
  'userObjectClasses': ['inetOrgPerson, organizationalPerson, person'],
  'connectionUrl': [ldap_url],
  'usersDn': [users_ou],
  'authType': ['simple'],
  'bindDn': [kc_bind],
  'bindCredential': [kc_pw],
  'searchScope': ['1'],
  'trustEmail': ['true'],
  'useTruststoreSpi': ['ldapsOnly'],
  'connectionPooling': ['true'],
  'connectionTimeout': ['10000'],
  'readTimeout': ['10000'],
  'pagination': ['true'],
  'startTls': ['false'],
}}
payload = {{
  'name': 'bibliolatino-ldap',
  'providerId': 'ldap',
  'providerType': 'org.keycloak.storage.UserStorageProvider',
  'parentId': realm_id,
  'config': config,
}}
if existing:
    cid = existing[0]['id']
    payload['id'] = cid
    req(f'{{kc}}/admin/realms/library/components/{{cid}}', 'PUT', payload)
    print('updated', cid)
else:
    req(f'{{kc}}/admin/realms/library/components', 'POST', payload)
    _, comps = req(f'{{kc}}/admin/realms/library/components?type=org.keycloak.storage.UserStorageProvider')
    cid = next(c['id'] for c in comps if c.get('name')=='bibliolatino-ldap')
    print('created', cid)

# Test connection
try:
    req(f'{{kc}}/admin/realms/library/user-storage/{{cid}}/sync?action=triggerFullSync', 'POST', {{}})
    print('sync triggered')
except Exception as e:
    print('sync note', e)

import time; time.sleep(2)
_, users = req(f'{{kc}}/admin/realms/library/users?max=30')
print('users', len(users or []))
for u in (users or [])[:15]:
    print('-', u.get('username'), u.get('email'), 'fed', bool(u.get('federationLink')))
"""
    sftp = proxy.open_sftp()
    with sftp.file("/tmp/kc_ldap_fed.py", "w") as f:
        f.write(script)
    sftp.close()
    stdin, stdout, stderr = proxy.exec_command("python3 /tmp/kc_ldap_fed.py", timeout=120)
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err:
        print("ERR", err[-2000:])
    proxy.close()
    print("LDAP federation configure done.")


if __name__ == "__main__":
    main()
