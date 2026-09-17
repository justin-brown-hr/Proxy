#!/usr/bin/env bash
# Milestone 2 checks (simulator rewrite + resource routes). Requires SSO cookie
# for protected paths — unauthenticated checks only verify redirects.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
[[ -f "$ROOT/.env" ]] && source "$ROOT/.env"

BASE="${BASE_URL:-${APP_URL:-https://proxy.bibliolatino.com}}"
BASE="${BASE%/}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "OK: $*"; }

echo "==> Portal /databases.html requires auth (302 to oauth2)"
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/databases.html")
[[ "$code" == "302" || "$code" == "401" ]] || fail "databases.html expected 302/401, got $code"
pass "databases.html gated ($code)"

echo "==> Simulator route /r/simulator/ requires auth"
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/r/simulator/")
[[ "$code" == "302" || "$code" == "401" ]] || fail "/r/simulator/ expected 302/401, got $code"
pass "/r/simulator/ gated ($code)"

echo "==> Live routes exist (gated)"
for name in sciencedirect scopus iop; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/r/${name}/")
  [[ "$code" == "302" || "$code" == "401" || "$code" == "502" || "$code" == "503" ]] \
    || fail "/r/${name}/ unexpected $code"
  pass "/r/${name}/ responds ($code)"
done

echo "==> Generated stanza config present"
[[ -f "$ROOT/nginx/resources.locations.conf" ]] || fail "missing resources.locations.conf — run generate-proxy-conf.py"
grep -q 'location /r/simulator/' "$ROOT/nginx/resources.locations.conf" || fail "simulator location missing"
grep -q 'location /r/sciencedirect/' "$ROOT/nginx/resources.locations.conf" || fail "sciencedirect location missing"
pass "resources.locations.conf contains expected locations"

echo
echo "Milestone 2 smoke checks passed."
echo "After login, open ${BASE}/databases.html and test the simulator for URL rewrite."
echo "Live ScienceDirect/Scopus/IOP need IP whitelist: confirm 169.58.217.137 with providers."
