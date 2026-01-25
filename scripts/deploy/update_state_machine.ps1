param (
    [string]$Profile = "my-dev",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

$RepoRootPath = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path

function Assert-Command ($Command) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        Write-Error "$Command is not installed or not in the PATH."
        exit 1
    }
}

Assert-Command "aws"

Write-Host "Fetching Lambda ARNs..."
function Get-LambdaArn ($FunctionName) {
    $Arn = (aws lambda get-function --function-name $FunctionName --profile $Profile --region $Region --output text --query Configuration.FunctionArn --no-cli-pager)
    if (-not $Arn) { Write-Error "Could not find ARN for $FunctionName"; exit 1 }
    return $Arn
}

$SummarizationArn = Get-LambdaArn "ICPA-Summarization-Lambda"
$RouterArn = Get-LambdaArn "ICPA-Router-Lambda"
$FraudAgentArn = Get-LambdaArn "ICPA-Fraud-Agent-Lambda"
$AdjudicationAgentArn = Get-LambdaArn "ICPA-Adjudication-Agent-Lambda"
$NotificationArn = Get-LambdaArn "ICPA-Notification-Lambda"
$PersistTerminalStateArn = Get-LambdaArn "ICPA-Terminal-State-Lambda"

Write-Host "Reading State Machine Definition..."
$ASLFile = Join-Path $RepoRootPath "infra\\state-machines\\claim_orchestration.asl.json"
$ASLContent = Get-Content $ASLFile -Raw

# Substitute Placeholders
$ASLContent = $ASLContent.Replace('${SummarizationLambdaArn}', $SummarizationArn)
$ASLContent = $ASLContent.Replace('${RouterLambdaArn}', $RouterArn)
$ASLContent = $ASLContent.Replace('${InvokeFraudAgentLambdaArn}', $FraudAgentArn)
$ASLContent = $ASLContent.Replace('${InvokeAdjAgentLambdaArn}', $AdjudicationAgentArn)
$ASLContent = $ASLContent.Replace('${NotificationLambdaArn}', $NotificationArn)
$ASLContent = $ASLContent.Replace('${PersistTerminalStateLambdaArn}', $PersistTerminalStateArn)

$DistDir = Join-Path $RepoRootPath "dist"
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }
$DefFile = Join-Path $DistDir "resolved_state_machine.json"
$ASLContent | Out-File -FilePath $DefFile -Encoding ascii

Write-Host "Updating State Machine..."
$AccountID = (aws sts get-caller-identity --profile $Profile --output text --query Account --no-cli-pager)
$StateMachineArn = "arn:aws:states:$Region`:$AccountID`:stateMachine:ICPA-Claim-Orchestration"

aws stepfunctions update-state-machine --state-machine-arn $StateMachineArn --definition "file://$DefFile" --profile $Profile --region $Region --no-cli-pager

Write-Host "State Machine updated successfully."
