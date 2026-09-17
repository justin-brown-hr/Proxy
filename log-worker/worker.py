"""Tail Nginx library_access logs and insert into analytics.access_events."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

import psycopg

LOG_PATH = Path(os.environ.get("NGINX_ACCESS_LOG", "/var/log/nginx/access.log"))
DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://keycloak:keycloak@postgres:5432/analytics",
)
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "2"))
SCHEMA_PATH = Path(os.environ.get("SCHEMA_PATH", "/app/schema.sql"))

LINE_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>\S+)(?: \S+)?" (?P<status>\d+) (?P<bytes>\S+) '
    r'"(?P<referer>[^"]*)" "(?P<ua>[^"]*)" '
    r'user="(?P<user>[^"]*)" email="(?P<email>[^"]*)" '
    r'campus="(?P<campus>[^"]*)" resource="(?P<resource>[^"]*)"'
)

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

INSERT_SQL = """
INSERT INTO access_events (
    event_time, remote_addr, method, path, status, bytes_sent,
    referer, user_agent, username, email, campus, resource, content_type, raw_line
) VALUES (
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s
)
"""


def parse_time(s: str) -> datetime:
    day, mon, rest = s.split("/", 2)
    year_time, tz = rest.rsplit(" ", 1)
    year, hms = year_time.split(":", 1)
    hour, minute, second = hms.split(":")
    sign = 1 if tz[0] == "+" else -1
    tzh, tzm = int(tz[1:3]), int(tz[3:5])
    naive = datetime(int(year), MONTHS[mon], int(day), int(hour), int(minute), int(second))
    offset = timedelta(hours=sign * tzh, minutes=sign * tzm)
    return (naive - offset).replace(tzinfo=timezone.utc)


def classify_content(path: str) -> str:
    p = unquote(path or "").lower()
    if any(p.endswith(ext) for ext in (".pdf", ".epub", ".djvu")):
        return "pdf"
    if any(p.endswith(ext) for ext in (".mp4", ".webm", ".m3u8", ".mp3", ".mov")):
        return "video"
    if "/video" in p or "/videos/" in p:
        return "video"
    if any(
        p.endswith(ext)
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css", ".js", ".woff", ".woff2", ".ico", ".map")
    ):
        return "asset"
    if p.startswith("/oauth2") or p.startswith("/realms/") or p.startswith("/admin/"):
        return "auth"
    if p.startswith("/r/") or p.startswith("/databases"):
        return "article"
    if p in ("/", "/healthz") or p.startswith("/assets/") or p.startswith("/guest/"):
        return "portal"
    return "other"


def ensure_schema(conn: psycopg.Connection) -> None:
    if not SCHEMA_PATH.exists():
        return
    # Run statements one-by-one (psycopg may not like multi-statement + views together)
    sql = SCHEMA_PATH.read_text()
    parts = [p.strip() for p in sql.split(";") if p.strip()]
    for part in parts:
        conn.execute(part)
    conn.commit()


def parse_line(line: str) -> tuple | None:
    m = LINE_RE.match(line.strip())
    if not m:
        return None
    g = m.groupdict()
    try:
        event_time = parse_time(g["time"])
    except Exception:
        event_time = datetime.now(timezone.utc)
    bytes_sent = 0 if g["bytes"] == "-" else int(g["bytes"])
    campus = g["campus"] in ("1", "true", "True", "yes")
    path = g["path"]
    return (
        event_time,
        g["ip"],
        g["method"],
        path,
        int(g["status"]),
        bytes_sent,
        g["referer"],
        g["ua"],
        g["user"] or None,
        g["email"] or None,
        campus,
        g["resource"] if g["resource"] != "-" else None,
        classify_content(path),
        line.strip()[:2000],
    )


def follow_lines(path: Path):
    """Poll file by byte offset (works even when stream APIs dislike seek)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    offset = 0
    inode = None
    # Start at EOF so we don't re-ingest huge historical logs on first boot
    if path.exists():
        offset = path.stat().st_size
        inode = path.stat().st_ino
    while True:
        try:
            if not path.exists():
                time.sleep(POLL_SECONDS)
                continue
            st = path.stat()
            if inode is not None and (st.st_ino != inode or st.st_size < offset):
                offset = 0
                inode = st.st_ino
            if st.st_size == offset:
                time.sleep(POLL_SECONDS)
                continue
            with path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                data = f.read()
                offset = f.tell()
            inode = st.st_ino
            for line in data.splitlines():
                if line.strip():
                    yield line
        except Exception as exc:
            print(f"follow error: {exc}", flush=True)
            time.sleep(POLL_SECONDS)


def main() -> None:
    print(f"log-worker starting; log={LOG_PATH} db=...@{DSN.split('@')[-1]}", flush=True)
    while True:
        try:
            with psycopg.connect(DSN) as conn:
                ensure_schema(conn)
                print("connected to analytics db", flush=True)
                batch: list[tuple] = []
                last_flush = time.time()
                for line in follow_lines(LOG_PATH):
                    row = parse_line(line)
                    if row:
                        batch.append(row)
                    now = time.time()
                    if batch and (len(batch) >= 50 or now - last_flush >= 5):
                        with conn.cursor() as cur:
                            cur.executemany(INSERT_SQL, batch)
                        conn.commit()
                        print(f"ingested {len(batch)} events", flush=True)
                        batch.clear()
                        last_flush = now
        except Exception as exc:
            print(f"worker error: {exc}; retry in 5s", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
