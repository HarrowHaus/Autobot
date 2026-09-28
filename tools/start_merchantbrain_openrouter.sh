#!/usr/bin/env bash
set -euo pipefail
: "${OPENROUTER_API_KEY:?Set OPENROUTER_API_KEY first}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AICOM="$ROOT/.runtime/aicom"
mkdir -p "$ROOT/.runtime"
if [ ! -d "$AICOM/.git" ]; then
  git clone --depth 1 --recurse-submodules https://github.com/alexar76/aicom.git "$AICOM"
else
  git -C "$AICOM" pull --ff-only
fi
cp "$AICOM/.env.demo" "$AICOM/.env"
cat >>"$AICOM/.env" <<EOF
OPENROUTER_API_KEY=$OPENROUTER_API_KEY
AIFACTORY_AUTONOMOUS_PIPELINE=1
AIFACTORY_DISCOVERY_AUTO_ENQUEUE=0
AIFACTORY_LLM_MAX_PARALLEL_REQUESTS=1
AIFACTORY_LLM_MAX_REQUESTS_PER_MINUTE=6
AIFACTORY_LLM_DAILY_COST_CAP_USD=0
AIFACTORY_LLM_MONTHLY_COST_CAP_USD=0
AIFACTORY_LLM_CACHE_ENABLED=1
EOF
mkdir -p "$AICOM/data/config"
cp "$ROOT/integrations/aicom/model_providers.openrouter-free.yaml" "$AICOM/data/config/model_providers.yaml"
cd "$AICOM"
./start.sh --no-open
echo "AI-Factory: http://localhost:9080"
