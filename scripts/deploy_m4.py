#!/usr/bin/env python3
"""Deploy Milestone 4 to proxy.bibliolatino.com"""
from __future__ import annotations

import io
import tarfile
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]


def load(p: Path) -> dict[str, str]:
    e: dict[str, str] = {}
    if not p.exists():
        return e
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        e[k.strip()] = v.strip()
    return e


def main() -> None:
    creds = load(ROOT / "docs" / "credentials.env")
    dotenv = load(ROOT / ".env")

    files = [
        "docker-compose.yml",
        ".env.example",
        "README.md",
        "nginx/conf.d/default.conf",
        "nginx/nginx.conf",
        "scripts/analytics-schema.sql",
        "scripts/init-analytics-db.sql",
        "scripts/validate-m4.sh",
        "scripts/configure_ldap_federation.py",
        "scripts/configure-ldap-federation.sh",
        "log-worker/Dockerfile",
        "log-worker/worker.py",
        "log-worker/requirements.txt",
        "log-worker/schema.sql",
        "guest-portal/Dockerfile",
        "guest-portal/requirements.txt",
        "guest-portal/app/main.py",
        "guest-portal/app/config.py",
        "guest-portal/app/ldap_guests.py",
        "guest-portal/app/keycloak_admin.py",
    ]

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in files:
            p = ROOT / rel
            if p.exists():
                tar.add(p, arcname=rel)
    buf.seek(0)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        creds["PROXY_IP"],
        username=creds["PROXY_USER"],
        password=creds["PROXY_PASS"],
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )

    def run(cmd: str, t: int = 600) -> tuple[int, str]:
        print(f"\n=== {cmd[:140]}")
        stdin, stdout, stderr = client.exec_command(cmd, timeout=t)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        code = stdout.channel.recv_exit_status()
        if out:
            print(out[-6000:])
        if err:
            print("ERR", err[-3000:])
        print("exit", code)
        return code, out

    sftp = client.open_sftp()
    with sftp.file("/tmp/m4.tgz", "wb") as f:
        f.write(buf.read())

    ldap_lines = "\n".join(
        [
            f"LDAP_URL={dotenv.get('LDAP_URL', '')}",
            f"LDAP_BASE_DN={dotenv.get('LDAP_BASE_DN', '')}",
            f"LDAP_USERS_OU={dotenv.get('LDAP_USERS_OU', '')}",
            f"LDAP_KC_BIND_DN={dotenv.get('LDAP_KC_BIND_DN', '')}",
            f"LDAP_KC_BIND_PASSWORD={dotenv.get('LDAP_KC_BIND_PASSWORD', '')}",
            f"LDAP_BIND_DN={dotenv.get('LDAP_BIND_DN', '')}",
            f"LDAP_BIND_PASSWORD={dotenv.get('LDAP_BIND_PASSWORD', '')}",
        ]
    )
    with sftp.file("/tmp/ldap.env.snippet", "w") as f:
        f.write(ldap_lines + "\n")

    merge_py = r'''
from pathlib import Path
snip = Path("/tmp/ldap.env.snippet").read_text().splitlines()
env_path = Path("/opt/library-proxy/.env")
text = env_path.read_text() if env_path.exists() else ""
keys = {}
for line in snip:
    if "=" in line:
        k, v = line.split("=", 1)
        keys[k] = v
for k, v in keys.items():
    if f"{k}=" in text:
        lines = []
        for line in text.splitlines():
            lines.append(f"{k}={v}" if line.startswith(f"{k}=") else line)
        text = "\n".join(lines) + "\n"
    else:
        text = text.rstrip() + f"\n{k}={v}\n"
env_path.write_text(text)
print("remote .env LDAP updated")
'''
    with sftp.file("/tmp/merge_ldap_env.py", "w") as f:
        f.write(merge_py)
    sftp.close()

    run("cd /opt/library-proxy && tar xzf /tmp/m4.tgz && python3 /tmp/merge_ldap_env.py")
    run(
        "docker exec library-postgres psql -U keycloak -d keycloak -tc "
        "\"SELECT 1 FROM pg_database WHERE datname='analytics'\" | grep -q 1 "
        "|| docker exec library-postgres psql -U keycloak -d keycloak -c 'CREATE DATABASE analytics;'"
    )
    run(
        "docker exec library-postgres psql -U keycloak -d keycloak -tc "
        "\"SELECT 1 FROM pg_database WHERE datname='metabase'\" | grep -q 1 "
        "|| docker exec library-postgres psql -U keycloak -d keycloak -c 'CREATE DATABASE metabase;'"
    )
    run(
        "docker exec -i library-postgres psql -U keycloak -d analytics "
        "< /opt/library-proxy/scripts/analytics-schema.sql"
    )
    run(
        "cd /opt/library-proxy && docker compose build guest-portal log-worker "
        "&& docker compose up -d postgres metabase log-worker guest-portal nginx",
        t=700,
    )
    run('docker compose -f /opt/library-proxy/docker-compose.yml ps --format "table {{.Name}}\\t{{.Status}}"')
    run("docker exec library-nginx nginx -t && docker exec library-nginx nginx -s reload")
    client.close()
    print("DEPLOY_SYNC_DONE")


if __name__ == "__main__":
    main()
