#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
[[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
BASE="${BASE_URL:-${APP_URL:-https://proxy.bibliolatino.com}}"
BASE="${BASE%/}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "OK: $*"; }

echo "==> Public guest registration page"
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/guest/")
[[ "$code" == "200" ]] || fail "/guest/ expected 200, got $code"
pass "/guest/ is public ($code)"

echo "==> Guest register API rejects empty body"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE}/guest/api/register" -H 'Content-Type: application/json' -d '{}')
[[ "$code" == "422" || "$code" == "400" ]] || fail "register expected 422, got $code"
pass "register validates input ($code)"

echo "==> Admin panel requires auth"
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/guest/admin")
[[ "$code" == "302" || "$code" == "401" ]] || fail "/guest/admin expected 302/401, got $code"
pass "/guest/admin gated ($code)"

echo "==> Guest health"
curl -fsS "${BASE}/guest/healthz" | grep -q ok || fail "guest healthz failed"
pass "guest healthz ok"

echo
echo "Milestone 3 smoke checks passed."
echo "Manual: open ${BASE}/guest/ to register; approve at ${BASE}/guest/admin as librarian/admin123"
