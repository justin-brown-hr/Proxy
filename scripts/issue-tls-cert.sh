#!/usr/bin/env bash
# Issue or renew Let's Encrypt cert and copy into ./certs for Nginx.
set -euo pipefail

DOMAIN="${PUBLIC_HOST:-proxy.bibliolatino.com}"
EMAIL="${CERTBOT_EMAIL:-admin@${DOMAIN}}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CERT_DIR="$ROOT/certs"

mkdir -p "$CERT_DIR" "$ROOT/certbot-www"

if ! command -v certbot >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y certbot
fi

# Free port 80 for standalone challenge
cd "$ROOT"
docker compose stop nginx || true

certbot certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  -d "$DOMAIN" \
  --keep-until-expiring \
  --preferred-challenges http

cp -L "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" "$CERT_DIR/fullchain.pem"
cp -L "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" "$CERT_DIR/privkey.pem"
chmod 644 "$CERT_DIR/fullchain.pem"
chmod 600 "$CERT_DIR/privkey.pem"

docker compose start nginx || docker compose up -d nginx

echo "Certificate ready in ${CERT_DIR}"
