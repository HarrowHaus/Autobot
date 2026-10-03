param([string]$OpenRouterKey=$env:OPENROUTER_API_KEY)
$ErrorActionPreference="Stop"
if (-not $OpenRouterKey) { throw "Set OPENROUTER_API_KEY first." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is required." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker Desktop / Docker Compose is required." }

$root=(Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$vendor=Join-Path $root ".runtime"
$aicom=Join-Path $vendor "aicom"
New-Item -ItemType Directory -Force $vendor | Out-Null

if (-not (Test-Path (Join-Path $aicom ".git"))) {
  git clone --depth 1 --recurse-submodules https://github.com/alexar76/aicom.git $aicom
} else {
  git -C $aicom pull --ff-only
}
Copy-Item (Join-Path $aicom ".env.demo") (Join-Path $aicom ".env") -Force
Add-Content (Join-Path $aicom ".env") @"

OPENROUTER_API_KEY=$OpenRouterKey
AIFACTORY_AUTONOMOUS_PIPELINE=1
AIFACTORY_DISCOVERY_AUTO_ENQUEUE=0
AIFACTORY_LLM_MAX_PARALLEL_REQUESTS=1
AIFACTORY_LLM_MAX_REQUESTS_PER_MINUTE=6
AIFACTORY_LLM_DAILY_COST_CAP_USD=0
AIFACTORY_LLM_MONTHLY_COST_CAP_USD=0
AIFACTORY_LLM_CACHE_ENABLED=1
"@
New-Item -ItemType Directory -Force (Join-Path $aicom "data/config") | Out-Null
Copy-Item (Join-Path $root "integrations/aicom/model_providers.openrouter-free.yaml") (Join-Path $aicom "data/config/model_providers.yaml") -Force
Write-Host "Starting upstream AI-Factory core with native OpenRouter provider..."
Push-Location $aicom
try { bash ./start.sh --no-open } finally { Pop-Location }
Write-Host ""
Write-Host "AI-Factory: http://localhost:9080"
Push-Location $root
try { python -m swarmbrain.opportunity_factory } finally { Pop-Location }
$product = Get-Content (Join-Path $root "reports/merchantbrain/product.json") -Raw | ConvertFrom-Json
if ($product.status -eq "publishable") {
  $idea = "$($product.promise) Buyer: $($product.buyer). Evidence-led opportunity selected autonomously by MerchantBrain. Build the smallest polished saleable web product that fulfills this need."
  Push-Location $aicom
  try {
    $env:DEMO_BASE_URL="http://localhost:9080"
    bash ./demo.sh --landing --no-open --compose $idea
  } finally { Pop-Location }
} else {
  Write-Host "MerchantBrain abstained: no opportunity passed the evidence threshold."
}
