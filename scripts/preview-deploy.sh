#!/usr/bin/env bash
# Spin up a throwaway, fully-working preview deployment with zero Cloudflare
# login required -- uses `wrangler deploy --temporary`, which mints an
# anonymous account good for ~1 hour unless claimed.
#
# Useful for demoing a change without needing Cloudflare login at all.
# Not meant to replace the real deploy path (Cloudflare's Git integration,
# see README) -- the temp account's D1/KV are separate from the real ones
# and disappear when the account expires or is claimed elsewhere.
#
# Usage: ./scripts/preview-deploy.sh

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "==> Minting a temporary Cloudflare account (no bindings yet)..."
# wrangler resolves `main`/`directory` relative to the config file's own
# location, not the CWD -- so these must be absolute paths since the config
# lives outside the repo (in /tmp).
cat > /tmp/wrangler-preview-bootstrap.toml <<EOF
name = "payoutsplit"
main = "$ROOT/src/index.ts"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]

[assets]
directory = "$ROOT/public"
binding = "ASSETS"

[vars]
ENVIRONMENT = "preview"
EOF

npm run generate:pages
npx wrangler deploy --temporary -c /tmp/wrangler-preview-bootstrap.toml

WRANGLER_HOME="${XDG_CONFIG_HOME:-$HOME/.config}/.wrangler"
CREDS_FILE="$WRANGLER_HOME/wrangler-temporary-account.toml"
if [[ ! -f "$CREDS_FILE" ]]; then
  echo "Couldn't find temporary account credentials at $CREDS_FILE" >&2
  exit 1
fi

TOKEN=$(grep '^apiToken' "$CREDS_FILE" | sed -E 's/apiToken = "(.*)"/\1/')
ACCOUNT_ID=$(grep '^id' "$CREDS_FILE" | head -1 | sed -E 's/id = "(.*)"/\1/')
CLAIM_URL=$(grep '^url' "$CREDS_FILE" | sed -E 's/url = "(.*)"/\1/')
EXPIRES=$(grep '^expiresAt' "$CREDS_FILE" | tail -1 | sed -E 's/expiresAt = "(.*)"/\1/')

export CLOUDFLARE_API_TOKEN="$TOKEN"
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"

echo "==> Creating preview D1 database..."
D1_OUTPUT=$(npx wrangler d1 create payoutsplit-preview 2>&1)
echo "$D1_OUTPUT"
D1_ID=$(echo "$D1_OUTPUT" | grep 'database_id' | sed -E 's/.*"([0-9a-f-]{36})".*/\1/')

echo "==> Creating preview KV namespace..."
KV_OUTPUT=$(npx wrangler kv namespace create payoutsplit_preview_cache 2>&1)
echo "$KV_OUTPUT"
KV_ID=$(echo "$KV_OUTPUT" | grep '^id' | sed -E 's/id = "(.*)"/\1/')

PREVIEW_CONFIG=/tmp/wrangler-preview-full.toml
cat > "$PREVIEW_CONFIG" <<EOF
name = "payoutsplit"
main = "$ROOT/src/index.ts"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]

[assets]
directory = "$ROOT/public"
binding = "ASSETS"

[[d1_databases]]
binding = "DB"
database_name = "payoutsplit-preview"
database_id = "$D1_ID"
migrations_dir = "migrations"

[[kv_namespaces]]
binding = "CACHE"
id = "$KV_ID"

[vars]
ENVIRONMENT = "preview"
EOF

echo "==> Applying schema..."
npx wrangler d1 execute payoutsplit-preview --remote --file=migrations/0001_init.sql -c "$PREVIEW_CONFIG"

echo "==> Deploying..."
npx wrangler deploy -c "$PREVIEW_CONFIG"

echo
echo "==> Preview is live. It runs on a throwaway account and expires at: $EXPIRES"
echo "==> Claim it into a permanent account (optional) here: $CLAIM_URL"
