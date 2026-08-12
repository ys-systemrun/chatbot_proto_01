# destroy.ps1 - tear down verify resources (IMPL-202608101542 section 9 last item / section 10 cost mgmt)
# Invoked by destroy.bat. The state bucket (bootstrap) is out of scope (delete manually).

. (Join-Path $PSScriptRoot "common.ps1")

Import-Config      # load .env (credentials / state bucket) before checking AWS auth
Test-Prerequisites

$tf     = Get-Tfvars
$region = $tf["aws_region"]
$env:AWS_DEFAULT_REGION = $region

Write-Step "リソース破棄"
Write-Warn "envs/verify の全リソース（VPC / RDS / ECS / ECR 等）を削除します。RDS のデータも失われます。"
$confirm = Read-Host "本当に破棄する場合は 'destroy' と入力してください"
if ($confirm -ne "destroy") { Write-Host "中止しました。"; exit 0 }

Push-Location $script:VerifyDir
try {
    Invoke-Checked {
        terraform init -input=false -reconfigure `
            -backend-config="bucket=$($script:StateBucket)" `
            -backend-config="region=$region" `
            -backend-config="key=chatbot-invitro/verify.tfstate" `
            -backend-config="use_lockfile=true"
    } "verify init"

    # knowledge_mcp_desired_count only matters on apply, but pass it so the variable resolves on destroy too
    Invoke-Checked {
        terraform destroy -auto-approve -input=false -var "knowledge_mcp_desired_count=0"
    } "destroy"
}
finally { Pop-Location }

Write-Ok "破棄完了"
Write-Info "state バケット（$($script:StateBucket)）は残っています。不要なら手動で削除してください。"
