param(
  [string]$Repo = "HarrowHaus/Autobot",
  [string]$Branch = "claude/monetizable-project-concepts-b97bv2"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI (gh) is not installed."
}

$activeLogin = (gh api user --jq .login 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($activeLogin)) {
  throw "GitHub CLI has no usable active account. Run: gh auth login"
}

if ($activeLogin.Trim() -ne "HarrowHaus") {
  throw "GitHub CLI active account is '$($activeLogin.Trim())', but this repo expects HarrowHaus."
}

Write-Host "GitHub active account: $($activeLogin.Trim())" -ForegroundColor Green

Write-Host ""
Write-Host "Paste rook's Clawlancer API key." -ForegroundColor Cyan
Write-Host "It will be hidden and will NOT be written to the repo or printed." -ForegroundColor DarkGray
$secure = Read-Host "CLAWLANCER_API_KEY" -AsSecureString

$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  $plain = $plain.Trim()

  if (($plain.StartsWith('"') -and $plain.EndsWith('"')) -or ($plain.StartsWith("'") -and $plain.EndsWith("'"))) {
    $plain = $plain.Substring(1, $plain.Length - 2).Trim()
  }

  if (-not $plain.StartsWith("clw_")) {
    throw "That does not look like a Clawlancer API key. Paste only the key itself, beginning with clw_."
  }

  $plain | gh secret set CLAWLANCER_API_KEY --repo $Repo
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to store CLAWLANCER_API_KEY in GitHub Actions Secrets."
  }
}
finally {
  if ($bstr -ne [IntPtr]::Zero) {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
  $plain = $null
  $secure = $null
}

Write-Host ""
Write-Host "Clawlancer secret stored." -ForegroundColor Green
Write-Host "Triggering the first earning cycle..." -ForegroundColor Cyan

gh workflow run clawlancer_earn.yml --repo $Repo --ref $Branch
if ($LASTEXITCODE -ne 0) {
  throw "Secret was stored, but the workflow could not be triggered."
}

Start-Sleep -Seconds 5
gh run list --repo $Repo --workflow clawlancer_earn.yml --limit 3

Write-Host ""
Write-Host "Activation complete. The worker also runs automatically on its schedule." -ForegroundColor Green
