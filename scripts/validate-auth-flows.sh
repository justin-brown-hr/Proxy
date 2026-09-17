#!/usr/bin/env bash
# Auth-flow checks: redirect loops, sign-out, HTTP→HTTPS, public paths.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
if [[ -f "$ROOT/.env" ]]; then
  source "$ROOT/.env"
fi

BASE="${BASE_URL:-${APP_URL:-http://localhost}}"
BASE="${BASE%/}"
HTTP_BASE="${BASE/https:/http:}"
HOST="${PUBLIC_HOST:-localhost}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "OK: $*"
}

# Returns final URL after following redirects (no body). Fails on loops.
follow_redirects() {
  local start="$1"
  local max="${2:-12}"
  local url="$start"
  local seen=""
  local i code loc

  for ((i = 1; i <= max; i++)); do
    if echo " $seen " | grep -q " ${url} "; then
      echo "LOOP:${url}"
      return 1
    fi
    seen="${seen} ${url}"

    loc=$(curl -sI --max-redirs 0 -o /dev/null -w '%{http_code} %{redirect_url}' "$url" 2>/dev/null || true)
    code="${loc%% *}"
    loc="${loc#* }"
    if [[ "$loc" == "$code" || -z "$loc" || "$loc" == " " ]]; then
      echo "$url"
      return 0
    fi
    url="$loc"
  done
  echo "TOOMANY:${url}"
  return 1
}

echo "==> Health endpoint (must not require auth)"
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/healthz")
[[ "$code" == "200" ]] || fail "/healthz expected 200, got $code"
pass "/healthz returns 200"

echo "==> OAuth paths must stay public (no 401 from nginx auth gate)"
for path in /oauth2/start /oauth2/callback; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}${path}")
  [[ "$code" != "401" ]] || fail "${path} returned 401 (likely behind auth_request)"
  pass "${path} is public ($code)"
done

echo "==> /logout must chain to Keycloak end-session (not loop)"
loc=$(curl -sI --max-redirs 0 "${BASE}/logout" | tr -d '\r' | awk 'tolower($1)=="location:" {print $2; exit}')
[[ -n "$loc" ]] || fail "/logout returned no Location header"
if [[ "$loc" != *"openid-connect/logout"* && "$loc" != *"openid-connect%2Flogout"* ]]; then
  fail "/logout must include Keycloak logout in redirect chain: $loc"
fi
pass "/logout chains to Keycloak logout"

echo "==> Sign out must not loop (ends on / or login, not sign_out)"
final=$(follow_redirects "${BASE}/logout" 15) || fail "redirect loop on /logout ($final)"
if [[ "$final" == *"/oauth2/sign_out"* ]]; then
  fail "/logout ends on sign_out: $final"
fi
pass "/logout flow ends at $final"

echo "==> Unauthenticated / should reach login (no redirect loop)"
final=$(follow_redirects "${BASE}/" 15) || fail "redirect loop on / ($final)"
if [[ "$final" != *"/realms/library"* && "$final" != *"/oauth2/"* ]]; then
  fail "unexpected final URL for /: $final"
fi
pass "/ ends at login flow ($final)"

echo "==> HTTP must redirect to HTTPS when BASE is https"
if [[ "$BASE" == https://* ]]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' "${HTTP_BASE}/")
  [[ "$code" == "301" || "$code" == "302" ]] || fail "http:// expected redirect, got $code"
  loc=$(curl -sI --max-redirs 0 "${HTTP_BASE}/" | tr -d '\r' | awk 'tolower($1)=="location:" {print $2; exit}')
  [[ "$loc" == https://* ]] || fail "http redirect Location is not https: $loc"
  pass "HTTP redirects to HTTPS ($loc)"
else
  echo "SKIP: BASE is not https ($BASE)"
fi

echo "==> Keycloak OIDC discovery reachable on public URL"
if [[ "$BASE" == https://* ]]; then
  curl -fsS "${BASE}/realms/library/.well-known/openid-configuration" | grep -q authorization_endpoint \
    || fail "OIDC discovery failed at ${BASE}/realms/library"
  pass "OIDC discovery on ${BASE}/realms/library"
else
  KC="${KEYCLOAK_URL:-http://localhost:8080}"
  curl -fsS "${KC}/realms/library/.well-known/openid-configuration" | grep -q authorization_endpoint \
    || fail "OIDC discovery failed at ${KC}"
  pass "OIDC discovery at ${KC}"
fi

echo
echo "All auth-flow checks passed for ${BASE}"
