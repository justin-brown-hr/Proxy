#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
[[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
BASE="${BASE_URL:-${APP_URL:-https://proxy.bibliolatino.com}}"
BASE="${BASE%/}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "OK: $*"; }

echo "==> Guest registration still public"
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/guest/")
[[ "$code" == "200" ]] || fail "/guest/ expected 200, got $code"
pass "/guest/ $code"

echo "==> Metabase responds"
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/metabase/")
[[ "$code" == "200" || "$code" == "301" || "$code" == "302" ]] || fail "/metabase/ expected 200/30x, got $code"
pass "/metabase/ $code"

echo "==> Analytics DB reachable from log-worker"
docker exec library-log-worker python -c "import psycopg,os; c=psycopg.connect(os.environ['DATABASE_URL']); c.execute('SELECT COUNT(*) FROM access_events'); print(c.fetchone())" \
  || fail "analytics query failed"
pass "access_events table OK"

echo "==> Log worker running"
docker inspect -f '{{.State.Running}}' library-log-worker | grep -q true || fail "log-worker not running"
pass "log-worker running"

echo
echo "Milestone 4 smoke checks passed."
echo "Next: open ${BASE}/metabase/ setup wizard; add DB host=postgres db=analytics user/password from .env"
echo "LDAP: run scripts/configure-ldap-federation.sh after docs/credentials.env is loaded"
