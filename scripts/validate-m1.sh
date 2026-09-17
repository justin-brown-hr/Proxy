#!/usr/bin/env bash
# Smoke-test Milestone 1 once the stack is up.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
if [[ -f "$ROOT/.env" ]]; then
  source "$ROOT/.env"
fi

BASE="${BASE_URL:-${APP_URL:-http://localhost}}"
BASE="${BASE%/}"

echo "==> Nginx health"
curl -fsS "${BASE}/healthz" | grep -q ok

echo "==> Keycloak realm discovery"
if [[ "$BASE" == https://* ]]; then
  curl -fsS "${BASE}/realms/library/.well-known/openid-configuration" | grep -q authorization_endpoint
else
  KC="${KEYCLOAK_URL:-http://localhost:8080}"
  curl -fsS "${KC}/realms/library/.well-known/openid-configuration" | grep -q authorization_endpoint
fi

echo "==> Unauthenticated / should redirect to oauth2 start (302)"
code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/")
if [[ "$code" != "302" && "$code" != "403" ]]; then
  echo "Expected 302/403 from /, got $code"
  exit 1
fi

echo "==> oauth2 start should redirect to Keycloak (302)"
code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/oauth2/start")
if [[ "$code" != "302" ]]; then
  echo "Expected 302 from /oauth2/start, got $code"
  exit 1
fi

echo "Milestone 1 smoke checks passed."
echo "Open ${BASE}/ and log in as demo / demo123 to finish manual SSO validation."
echo "Run ./scripts/validate-auth-flows.sh for redirect-loop and sign-out checks."
