param(
  [string]$Repo = "HarrowHaus/Autobot",
  [string]$Branch = "claude/monetizable-project-concepts-b97bv2",
  [string]$AgentName = "rook-cdp"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "GitHub CLI (gh) is not installed." }

$activeLogin = (gh api user --jq .login 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($activeLogin)) { throw "GitHub CLI has no usable active account. Run: gh auth login" }
if ($activeLogin.Trim() -ne "HarrowHaus") { throw "Wrong active GitHub account: $($activeLogin.Trim())" }

function Find-Field {
  param([Parameter(Mandatory=$true)]$Object,[Parameter(Mandatory=$true)][string[]]$Names,[int]$Depth = 0)
  if ($null -eq $Object -or $Depth -gt 6) { return $null }
  if ($Object -is [System.Collections.IDictionary]) {
    foreach ($name in $Names) {
      foreach ($key in $Object.Keys) {
        if ([string]::Equals([string]$key,$name,[System.StringComparison]::OrdinalIgnoreCase)) {
          $value = $Object[$key]
          if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) { return $value }
        }
      }
    }
    foreach ($key in $Object.Keys) {
      $found = Find-Field -Object $Object[$key] -Names $Names -Depth ($Depth + 1)
      if ($null -ne $found) { return $found }
    }
    return $null
  }
  if ($Object -is [System.Collections.IEnumerable] -and -not ($Object -is [string])) {
    foreach ($item in $Object) {
      $found = Find-Field -Object $item -Names $Names -Depth ($Depth + 1)
      if ($null -ne $found) { return $found }
    }
    return $null
  }
  foreach ($prop in $Object.PSObject.Properties) {
    foreach ($name in $Names) {
      if ([string]::Equals($prop.Name,$name,[System.StringComparison]::OrdinalIgnoreCase)) {
        $value = $prop.Value
        if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) { return $value }
      }
    }
  }
  foreach ($prop in $Object.PSObject.Properties) {
    $found = Find-Field -Object $prop.Value -Names $Names -Depth ($Depth + 1)
    if ($null -ne $found) { return $found }
  }
  return $null
}

$body = @{ agent_name = $AgentName; bio = "Autonomous research, coding, data-analysis, verification and planning worker."; wallet_provider = "cdp"; skills = @("research","coding","data-analysis","verification","planning") } | ConvertTo-Json -Compress
Write-Host "Registering a Clawlancer worker with wallet_provider=cdp..." -ForegroundColor Cyan

try { $response = Invoke-RestMethod -Uri "https://clawlancer.ai/api/agents/register" -Method Post -ContentType "application/json" -Body $body }
catch {
  $details = $_.ErrorDetails.Message
  if (-not $details -and $_.Exception.Response) {
    try {
      $stream = $_.Exception.Response.GetResponseStream()
      $reader = New-Object System.IO.StreamReader($stream)
      $details = $reader.ReadToEnd()
      $reader.Close()
    } catch {}
  }
  if ($details) { throw "Clawlancer registration failed: $details" }
  throw "Clawlancer registration failed with HTTP error and no response body."
}

$apiKey = [string](Find-Field -Object $response -Names @("api_key","apiKey"))
$agentId = [string](Find-Field -Object $response -Names @("agent_id","agentId","id"))
$wallet = [string](Find-Field -Object $response -Names @("wallet_address","walletAddress","wallet"))
$returnedName = [string](Find-Field -Object $response -Names @("name","agent_name","agentName"))

if ([string]::IsNullOrWhiteSpace($apiKey) -or -not $apiKey.StartsWith("clw_")) { throw "Clawlancer created a response but no usable API key was returned." }
if ([string]::IsNullOrWhiteSpace($agentId)) { throw "Clawlancer created a response but no agent ID was returned." }
if ([string]::IsNullOrWhiteSpace($returnedName)) { $returnedName = $AgentName }

$apiKey | gh secret set CLAWLANCER_API_KEY --repo $Repo
if ($LASTEXITCODE -ne 0) { throw "Failed to store CLAWLANCER_API_KEY." }
$returnedName | gh secret set CLAWLANCER_AGENT_NAME --repo $Repo
if ($LASTEXITCODE -ne 0) { throw "Failed to store CLAWLANCER_AGENT_NAME." }
$agentId | gh secret set CLAWLANCER_AGENT_ID --repo $Repo
if ($LASTEXITCODE -ne 0) { throw "Failed to store CLAWLANCER_AGENT_ID." }
if (-not [string]::IsNullOrWhiteSpace($wallet)) {
  $wallet | gh secret set CLAWLANCER_AGENT_WALLET --repo $Repo
  if ($LASTEXITCODE -ne 0) { throw "Failed to store CLAWLANCER_AGENT_WALLET." }
}

$apiKey = $null
Write-Host ""
Write-Host "CDP worker registered and stored in GitHub Secrets." -ForegroundColor Green
Write-Host "Name: $returnedName"
Write-Host "Agent ID: $agentId"
if ($wallet) { Write-Host "Worker wallet: $wallet" }
Write-Host ""
Write-Host "Triggering the Clawlancer earning cycle..." -ForegroundColor Cyan
gh workflow run clawlancer_earn.yml --repo $Repo --ref $Branch
if ($LASTEXITCODE -ne 0) { throw "Worker registration succeeded, but the earning workflow could not be triggered." }
Start-Sleep -Seconds 6
gh run list --repo $Repo --workflow clawlancer_earn.yml --limit 3
