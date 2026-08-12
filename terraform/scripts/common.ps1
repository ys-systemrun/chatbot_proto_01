# common.ps1 - shared helpers for deploy.ps1 / destroy.ps1 (Windows PowerShell 5.1 compatible)
# Do not run directly; dot-source it from each script.

$ErrorActionPreference = "Stop"

# Resolve terraform/ root and repo root (scripts/ -> terraform/ -> repo root)
$script:TfRoot   = Split-Path $PSScriptRoot -Parent
$script:RepoRoot = Split-Path $script:TfRoot -Parent
$script:VerifyDir    = Join-Path $script:TfRoot "envs\verify"
$script:BootstrapDir = Join-Path $script:TfRoot "bootstrap"
$script:TfvarsPath    = Join-Path $script:VerifyDir "terraform.tfvars"
$script:TfvarsExample = Join-Path $script:VerifyDir "terraform.tfvars.example"
$script:EnvPath    = Join-Path $PSScriptRoot ".env"
$script:EnvExample = Join-Path $PSScriptRoot ".env.example"

function Write-Step($msg)  { Write-Host "`n==== $msg ====" -ForegroundColor Cyan }
function Write-Info($msg)  { Write-Host "  $msg" -ForegroundColor Gray }
function Write-Ok($msg)    { Write-Host "  OK: $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "  WARN: $msg" -ForegroundColor Yellow }
function Fail($msg)        { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# Run an external command; stop if its exit code != 0.
function Invoke-Checked([scriptblock]$Block, [string]$What) {
    & $Block
    if ($LASTEXITCODE -ne 0) { Fail "$What に失敗しました (exit $LASTEXITCODE)" }
}

# y/N confirmation. Always proceeds when $script:AutoApprove is $true.
function Confirm-Or-Exit([string]$Message) {
    if ($script:AutoApprove) { Write-Info "(自動承認: $Message)"; return }
    $ans = Read-Host "$Message  続行しますか? [y/N]"
    if ($ans -ne "y" -and $ans -ne "Y") { Write-Host "中止しました。"; exit 0 }
}

# Verify required tools and credentials are available.
function Test-Prerequisites {
    Write-Step "前提ツール・認証の確認"
    foreach ($cmd in @("terraform", "aws", "docker")) {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
            Fail "$cmd が PATH に見つかりません。インストール/PATH設定を確認してください。"
        }
        Write-Ok "$cmd あり"
    }
    # Docker daemon must be running
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { Fail "Docker デーモンに接続できません。Docker Desktop を起動してください。" }
    Write-Ok "Docker デーモン稼働中"
    # AWS credentials must be valid
    $identity = aws sts get-caller-identity --query "Account" --output text 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($identity)) {
        Fail "AWS 認証情報が無効です。.env のアクセスキー / AWS_PROFILE / 既定クレデンシャルを確認してください。"
    }
    # Safety guard: refuse to deploy into an unexpected account.
    if (-not [string]::IsNullOrWhiteSpace($script:AwsAccountId) -and $identity -ne $script:AwsAccountId) {
        Fail "認証先アカウント($identity)が .env の AWS_ACCOUNT_ID($($script:AwsAccountId))と一致しません。"
    }
    Write-Ok "AWS 認証OK (Account: $identity)"
}

# Parse a KEY=VALUE file (.env / tfvars style) into a hashtable.
# Ignores blank lines and '#' comments; strips surrounding quotes from values.
function Read-KeyValueFile([string]$Path) {
    $map = @{}
    foreach ($line in Get-Content $Path) {
        $t = $line.Trim()
        if ($t -eq "" -or $t.StartsWith("#") -or -not $t.Contains("=")) { continue }
        $k = $t.Substring(0, $t.IndexOf("=")).Trim()
        $v = $t.Substring($t.IndexOf("=") + 1).Trim()
        $v = $v.Trim('"').Trim("'")
        $map[$k] = $v
    }
    return $map
}

# Load scripts/.env; if missing, create from .env.example and stop.
function Import-Config {
    if (-not (Test-Path $script:EnvPath)) {
        Copy-Item $script:EnvExample $script:EnvPath
        Fail "設定ファイルを作成しました: $($script:EnvPath)`n  STATE_BUCKET 等を記入してから再実行してください。"
    }
    $cfg = Read-KeyValueFile $script:EnvPath
    $bucket = $cfg["STATE_BUCKET"]
    if ([string]::IsNullOrWhiteSpace($bucket)) { Fail ".env の STATE_BUCKET が未設定です。" }
    $script:StateBucket = $bucket
    $script:AwsAccountId = $cfg["AWS_ACCOUNT_ID"]
    $script:AutoApprove  = $false  # may be overridden by the caller (deploy)

    # Credential resolution: explicit keys win; otherwise a named profile; otherwise default chain.
    $ak = $cfg["AWS_ACCESS_KEY_ID"]
    $sk = $cfg["AWS_SECRET_ACCESS_KEY"]
    $st = $cfg["AWS_SESSION_TOKEN"]
    $prof = $cfg["AWS_PROFILE"]
    if (-not [string]::IsNullOrWhiteSpace($ak) -and -not [string]::IsNullOrWhiteSpace($sk)) {
        # Avoid mixing with a stale profile in the environment.
        Remove-Item Env:AWS_PROFILE -ErrorAction SilentlyContinue
        $env:AWS_ACCESS_KEY_ID     = $ak
        $env:AWS_SECRET_ACCESS_KEY = $sk
        if (-not [string]::IsNullOrWhiteSpace($st)) { $env:AWS_SESSION_TOKEN = $st }
        else { Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue }
        Write-Info ".env のアクセスキーを使用"
    } elseif (-not [string]::IsNullOrWhiteSpace($prof)) {
        $env:AWS_PROFILE = $prof
        Write-Info "AWS_PROFILE=$prof を使用"
    } else {
        Write-Info "認証は既定のクレデンシャルチェーンを使用（.env に鍵/プロファイル指定なし）"
    }
}

# Parse terraform.tfvars into a hashtable (key = "value" / key = 123 form).
# If missing, create from example and stop.
function Get-Tfvars {
    if (-not (Test-Path $script:TfvarsPath)) {
        Copy-Item $script:TfvarsExample $script:TfvarsPath
        Fail "terraform.tfvars を作成しました: $($script:TfvarsPath)`n  発注者受領値（aws_account_id / aws_region / Bedrock モデルID / embedding_vector_dim 等）を記入してから再実行してください。"
    }
    return Read-KeyValueFile $script:TfvarsPath
}

# Ensure required tfvars keys are present and non-empty.
function Test-Tfvars($map) {
    $required = @("aws_region", "rds_engine_version", "bedrock_chat_model_id",
                  "bedrock_embedding_model_id", "embedding_vector_dim")
    $missing = @()
    foreach ($k in $required) {
        if (-not $map.ContainsKey($k) -or [string]::IsNullOrWhiteSpace($map[$k])) { $missing += $k }
    }
    if ($missing.Count -gt 0) {
        Fail "terraform.tfvars の必須項目が未設定です: $($missing -join ', ')`n  ファイル: $($script:TfvarsPath)"
    }
    Write-Ok "terraform.tfvars 必須項目OK"
}
