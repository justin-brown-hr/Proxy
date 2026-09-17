#!/usr/bin/env python3
"""Smoke-check M4 after deploy."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]


def load(p: Path) -> dict[str, str]:
    e: dict[str, str] = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        e[k.strip()] = v.strip()
    return e


def main() -> None:
    creds = load(ROOT / "docs" / "credentials.env")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        creds["PROXY_IP"],
        username=creds["PROXY_USER"],
        password=creds["PROXY_PASS"],
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )

    def run(cmd: str, t: int = 90) -> str:
        print("===", cmd[:100])
        stdin, stdout, stderr = c.exec_command(cmd, timeout=t)
        stdout.channel.settimeout(t)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        code = stdout.channel.recv_exit_status()
        text = (out + err)[-2500:]
        print(text)
        print("exit", code)
        return out

    run("docker exec library-nginx sh -c 'ls -la /var/log/nginx; wc -c /var/log/nginx/access.log'")
    run("docker exec library-log-worker sh -c 'ls -la /var/log/nginx; wc -c /var/log/nginx/access.log'")
    run(
        "docker exec library-nginx sh -c "
        "'tail -n 2 /var/log/nginx/access.log | cut -c1-200'"
    )

    run(
        "for i in 1 2 3 4 5 6 7 8; do "
        "curl -sk https://127.0.0.1/guest/healthz -H 'Host: proxy.bibliolatino.com' >/dev/null; "
        "done; sleep 7; "
        "docker logs library-log-worker --tail 25 2>&1; "
        "docker exec library-postgres psql -U keycloak -d analytics -tAc 'SELECT count(*) FROM access_events;'"
    )

    run("cd /opt/library-proxy && docker compose up -d --build guest-portal", t=300)
    run(
        "docker exec library-guest-portal python -c "
        "'from app.ldap_guests import ldap_guests; print(ldap_guests.enabled, ldap_guests.url)'"
    )

    email = f"guest.m4.{uuid.uuid4().hex[:8]}@example.com"
    body = json.dumps(
        {
            "email": email,
            "first_name": "M4",
            "last_name": "Guest",
            "password": "M4GuestTest12",
            "institution": "Test",
            "reason": "ldap check",
        }
    )
    sftp = c.open_sftp()
    with sftp.file("/tmp/m4_reg.json", "w") as f:
        f.write(body)
    sftp.close()
    run(
        "curl -sk -X POST https://127.0.0.1/guest/api/register "
        "-H 'Host: proxy.bibliolatino.com' -H 'Content-Type: application/json' "
        "-d @/tmp/m4_reg.json"
    )

    # Check LDAP from LDAP server via second connection
    ldap = paramiko.SSHClient()
    ldap.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ldap.connect(
        creds["LDAP_SERVER_IP"],
        username=creds["LDAP_SERVER_USER"],
        password=creds["LDAP_SERVER_PASS"],
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    bind_dn = creds["LDAP_KC_BIND_DN"]
    bind_pw = creds["LDAP_KC_BIND_PASSWORD"]
    users_ou = creds["LDAP_USERS_OU"]
    cmd = (
        f"ldapsearch -x -H ldap://127.0.0.1 -D '{bind_dn}' -w '{bind_pw}' "
        f"-b '{users_ou}' '(mail={email})' uid mail employeeType 2>&1 | head -30"
    )
    stdin, stdout, stderr = ldap.exec_command(cmd, timeout=30)
    print("LDAP lookup:\n", stdout.read().decode() + stderr.read().decode())
    ldap.close()

    run(
        "curl -sk -o /dev/null -w 'metabase:%{http_code}\\n' "
        "https://127.0.0.1/metabase/ -H 'Host: proxy.bibliolatino.com'"
    )
    c.close()
    print("EMAIL", email)


if __name__ == "__main__":
    main()
