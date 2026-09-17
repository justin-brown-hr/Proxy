-- Milestone 4 analytics schema (run against database `analytics`)
CREATE TABLE IF NOT EXISTS access_events (
    id              BIGSERIAL PRIMARY KEY,
    event_time      TIMESTAMPTZ NOT NULL,
    remote_addr     TEXT,
    method          TEXT,
    path            TEXT,
    status          INTEGER,
    bytes_sent      BIGINT,
    referer         TEXT,
    user_agent      TEXT,
    username        TEXT,
    email           TEXT,
    campus          BOOLEAN DEFAULT FALSE,
    resource        TEXT,
    content_type    TEXT NOT NULL DEFAULT 'other',
    raw_line        TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_access_events_time ON access_events (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_access_events_resource ON access_events (resource);
CREATE INDEX IF NOT EXISTS idx_access_events_content ON access_events (content_type);
CREATE INDEX IF NOT EXISTS idx_access_events_user ON access_events (username);
CREATE INDEX IF NOT EXISTS idx_access_events_email ON access_events (email);

CREATE OR REPLACE VIEW v_access_by_day AS
SELECT date_trunc('day', event_time) AS day,
       resource,
       content_type,
       COUNT(*) AS hits,
       COUNT(DISTINCT COALESCE(NULLIF(email, '-'), NULLIF(username, '-'), remote_addr)) AS unique_users
FROM access_events
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW v_access_by_resource AS
SELECT resource,
       content_type,
       COUNT(*) AS hits,
       COUNT(DISTINCT COALESCE(NULLIF(email, '-'), NULLIF(username, '-'), remote_addr)) AS unique_users
FROM access_events
WHERE resource IS NOT NULL AND resource <> '-'
GROUP BY 1, 2;
