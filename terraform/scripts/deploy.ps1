# deploy.ps1 - full pipeline deploy (IMPL-202608101542 section 7 / ADR-0030, 0034)
# Invoked by deploy.bat. Windows PowerShell 5.1 compatible.
#
# Flow:
#   prerequisites -> tfvars/config check -> Phase0 (state bucket) -> init (backend) ->
#   create ECR -> docker build/push x4 -> apply (knowledge_mcp=0) ->
#   run-task db_init and wait for exitCode=0 -> apply (knowledge_mcp=1) -> summary
#
# Phase 6 (MCP Inspector / interactive ipython tests) is out of scope for this script.

# -AutoApprove skips confirmation prompts (CI etc). Default is to confirm.
param([switch]$AutoApprove)

. (Join-Path $PSScriptRoot "common.ps1")

Import-Config      # load .env (credentials / state bucket) before checking AWS auth
Test-Prerequisites
if ($AutoApprove) { $script:AutoApprove = $true }

$tf     = Get-Tfvars
Test-Tfvars $tf
$region = $tf["aws_region"]
$imageTag = if ($tf.ContainsKey("image_tag") -and -not [string]::IsNullOrWhiteSpace($tf["image_tag"])) { $tf["image_tag"] } else { "latest" }
$env:AWS_DEFAULT_REGION = $region
Write-Info "region=$region / image_tag=$imageTag / state_bucket=$($script:StateBucket)"

Confirm-Or-Exit "AWS 上に VPC/RDS/ECS 等の課金リソースを作成します（リージョン: $region）。"

# ---------------------------------------------------------------------------
# Phase 0: Terraform state S3 bucket (bootstrap). Skip if it already exists.
# ---------------------------------------------------------------------------
Write-Step "Phase 0: Terraform state バケット"
aws s3api head-bucket --bucket $script:StateBucket *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Ok "state バケット既存: $($script:StateBucket)（bootstrap スキップ）"
} else {
    Write-Info "state バケットを作成します: $($script:StateBucket)"
    Push-Location $script:BootstrapDir
    try {
        Invoke-Checked { terraform init -input=false } "bootstrap init"
        Invoke-Checked {
            terraform apply -auto-approve -input=false `
                -var "aws_region=$region" -var "state_bucket_name=$($script:StateBucket)"
        } "bootstrap apply"
    } finally { Pop-Location }
    Write-Ok "state バケット作成完了"
}

# ---------------------------------------------------------------------------
# Main config init (S3 backend)
# ---------------------------------------------------------------------------
Write-Step "envs/verify init（S3 バックエンド）"
Push-Location $script:VerifyDir
try {
    Invoke-Checked {
        terraform init -input=false -reconfigure `
            -backend-config="bucket=$($script:StateBucket)" `
            -backend-config="region=$region" `
            -backend-config="key=chatbot-invitro/verify.tfstate" `
            -backend-config="use_lockfile=true"
    } "verify init"

    # -----------------------------------------------------------------------
    # Create ECR first (image push target)
    # -----------------------------------------------------------------------
    Write-Step "ECR リポジトリ作成"
    Invoke-Checked { terraform apply -auto-approve -input=false -target=module.ecr } "ECR apply"

    $repos = (terraform output -json ecr_repository_urls) | ConvertFrom-Json
    $registry = (($repos.'knowledge-mcp') -split '/')[0]

    # -----------------------------------------------------------------------
    # docker build / push x4 (reuse existing Dockerfiles, section 5.2).
    # mcp-inspector is for Phase 6 verification and is handled manually (section 5.7).
    # -----------------------------------------------------------------------
    Write-Step "Docker イメージ build / push"
    Write-Info "ECR ログイン: $registry"
    aws ecr get-login-password --region $region | docker login --username AWS --password-stdin $registry
    if ($LASTEXITCODE -ne 0) { Fail "ECR への docker login に失敗しました" }

    $components = @(
        @{ Dir = "knowledge_mcp";     Repo = "knowledge-mcp" },
        @{ Dir = "tag_selector_mcp";  Repo = "tag-selector-mcp" },
        @{ Dir = "agent_invitro";     Repo = "agent-invitro" },
        @{ Dir = "db_hiroba_qa_init"; Repo = "db-hiroba-qa-init" }
    )
    foreach ($c in $components) {
        $ctx = Join-Path $script:RepoRoot $c.Dir
        $img = "$($repos.($c.Repo)):$imageTag"
        Write-Info "build: $($c.Dir) -> $img"
        Invoke-Checked { docker build -t $img $ctx } "docker build ($($c.Dir))"
        Invoke-Checked { docker push $img } "docker push ($($c.Repo))"
    }
    Write-Ok "4イメージの push 完了"

    # -----------------------------------------------------------------------
    # Main apply (knowledge_mcp created with 0 tasks = Phase4->5 gate)
    # -----------------------------------------------------------------------
    Write-Step "インフラ apply（knowledge_mcp は seed 完了まで停止）"
    Invoke-Checked {
        terraform apply -auto-approve -input=false -var "knowledge_mcp_desired_count=0"
    } "本体 apply"

    # -----------------------------------------------------------------------
    # Phase 4: run db_hiroba_qa_init as a task and wait for exitCode=0
    # -----------------------------------------------------------------------
    Write-Step "Phase 4: DB マイグレーション・シード（run-task）"
    $cluster = terraform output -raw cluster_name
    $subnets = ((terraform output -json private_subnet_ids) | ConvertFrom-Json) -join ","
    $sg      = terraform output -raw sg_verification_task_id
    $family  = terraform output -raw db_init_task_family
    $net = "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$sg],assignPublicIp=DISABLED}"

    $taskArn = aws ecs run-task --cluster $cluster --launch-type FARGATE `
        --task-definition $family --enable-execute-command `
        --network-configuration $net --query "tasks[0].taskArn" --output text
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($taskArn) -or $taskArn -eq "None") {
        Fail "db_init の run-task 起動に失敗しました"
    }
    Write-Info "task: $taskArn"

    $timeoutSec = 1800; $elapsed = 0; $intervalSec = 15; $status = ""
    while ($true) {
        Start-Sleep -Seconds $intervalSec
        $elapsed += $intervalSec
        $status = aws ecs describe-tasks --cluster $cluster --tasks $taskArn `
            --query "tasks[0].lastStatus" --output text
        Write-Info "status=$status (${elapsed}s)"
        if ($status -eq "STOPPED") { break }
        if ($elapsed -ge $timeoutSec) { Fail "db_init がタイムアウトしました（${timeoutSec}s）。CloudWatch Logs /ecs/db-hiroba-qa-init を確認してください。" }
    }
    $exitCode = aws ecs describe-tasks --cluster $cluster --tasks $taskArn `
        --query "tasks[0].containers[0].exitCode" --output text
    if ($exitCode -ne "0") {
        Fail "db_init が異常終了しました (exitCode=$exitCode)。CloudWatch Logs /ecs/db-hiroba-qa-init を確認してください。"
    }
    Write-Ok "seed 完了（exitCode=0）"

    # -----------------------------------------------------------------------
    # Phase 5: start knowledge_mcp (release the gate)
    # -----------------------------------------------------------------------
    Write-Step "Phase 5: knowledge_mcp 起動"
    Invoke-Checked {
        terraform apply -auto-approve -input=false -var "knowledge_mcp_desired_count=1"
    } "knowledge_mcp 起動 apply"

    # -----------------------------------------------------------------------
    # Completion summary
    # -----------------------------------------------------------------------
    Write-Step "デプロイ完了"
    Write-Host ""
    Write-Host "  cluster : $cluster"
    Write-Host "  RDS     : $(terraform output -raw rds_endpoint)"
    Write-Host ""
    Write-Host "次の手動検証（Phase 6, README 参照）:" -ForegroundColor Cyan
    Write-Host "  - MCP Inspector 検証イメージを ECR(mcp-inspector) に push 後、run-task + ECS Exec"
    Write-Host "  - agent_invitro に ECS Exec(ipython) で接続し手動テストクエリ3件"
    Write-Host ""
    Write-Host "破棄する場合は destroy.bat を実行してください。" -ForegroundColor Yellow
}
finally { Pop-Location }
