#!/bin/sh
# Renders /usr/share/nginx/html/config.js from environment variables at container start.
# Runs automatically via the official nginx image's /docker-entrypoint.d/ hook.
set -eu

TARGET=/usr/share/nginx/html/config.js
RAW="${API_BASE_URL:-http://localhost:8000}"

# A URL never needs quotes, backslashes, angle brackets or whitespace; strip them so the
# value is always a safe JS string literal.
SAFE=$(printf '%s' "$RAW" | tr -d '"\\<>`[:space:]')
[ -n "$SAFE" ] || SAFE="http://localhost:8000"

cat > "$TARGET" <<JS
// Generated at container start by /docker-entrypoint.d/40-relay-config.sh
window.__RELAY_CONFIG__ = { API_BASE_URL: "${SAFE}" };
JS

echo "relay: wrote $TARGET (API_BASE_URL=${SAFE})"
