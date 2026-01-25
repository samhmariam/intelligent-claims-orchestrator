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

function Update-LambdaCodeIfExists ($FuncName, $ZipPath) {
    try {
        aws lambda get-function --function-name $FuncName --profile $Profile --region $Region --no-cli-pager | Out-Null
    }
    catch {
        Write-Warning "Skipping $FuncName (function not found). Run deploy_updates.ps1 to create it."
        return
    }
    aws lambda update-function-code --function-name $FuncName --zip-file "fileb://$ZipPath" --profile $Profile --region $Region --no-cli-pager
}

Write-Host "Packaging Ingestion Handler..."
$DistDir = Join-Path $RepoRootPath "dist"
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }

# Create temporary directory for packaging
$TempDir = Join-Path $DistDir "temp_ingestion"
if (Test-Path $TempDir) { Remove-Item -Path $TempDir -Recurse -Force }
New-Item -ItemType Directory -Path $TempDir | Out-Null

# Copy source files
$SrcRoot = Join-Path $RepoRootPath "src\\icpa"
Copy-Item -Path $SrcRoot -Destination $TempDir -Recurse
Copy-Item -Path (Join-Path $RepoRootPath "src\\icpa\\ingestion\\handlers.py") -Destination (Join-Path $TempDir "lambda_function.py")

# Zip it
$ZipFile = Join-Path $DistDir "ingestion_handler.zip"
if (Test-Path $ZipFile) { Remove-Item -Path $ZipFile -Force }
Compress-Archive -Path "$TempDir\*" -DestinationPath $ZipFile

# Cleanup
Remove-Item -Path $TempDir -Recurse -Force

Write-Host "Packaging Router Lambda..."
$TempDir = Join-Path $DistDir "temp_router"
if (Test-Path $TempDir) { Remove-Item -Path $TempDir -Recurse -Force }
New-Item -ItemType Directory -Path $TempDir | Out-Null

# Copy source files
Copy-Item -Path $SrcRoot -Destination $TempDir -Recurse
Copy-Item -Path (Join-Path $RepoRootPath "src\\icpa\\orchestration\\lambda_function.py") -Destination (Join-Path $TempDir "lambda_function.py")

# Zip it
$RouterZip = Join-Path $DistDir "router_lambda.zip"
if (Test-Path $RouterZip) { Remove-Item -Path $RouterZip -Force }
Compress-Archive -Path "$TempDir\*" -DestinationPath $RouterZip

# Cleanup
Remove-Item -Path $TempDir -Recurse -Force

Write-Host "Updating Lambda Code..."
Update-LambdaCodeIfExists "ICPA-Ingestion-Handler" $ZipFile
Update-LambdaCodeIfExists "ICPA-Textract-Result-Handler" $ZipFile
Update-LambdaCodeIfExists "ICPA-Transcribe-PostProcess-Handler" $ZipFile
Update-LambdaCodeIfExists "ICPA-Router-Lambda" $RouterZip
Update-LambdaCodeIfExists "ICPA-Fraud-Agent-Lambda" $RouterZip
Update-LambdaCodeIfExists "ICPA-Adjudication-Agent-Lambda" $RouterZip
Update-LambdaCodeIfExists "ICPA-Summarization-Lambda" $RouterZip
Update-LambdaCodeIfExists "ICPA-Notification-Lambda" $RouterZip
Update-LambdaCodeIfExists "ICPA-Terminal-State-Lambda" $RouterZip
Update-LambdaCodeIfExists "ICPA-HITL-Callback-Lambda" $RouterZip

Write-Host "Code update complete. You may now run the upload test."
