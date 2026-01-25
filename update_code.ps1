param (
    [string]$Profile = "my-dev",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

function Assert-Command ($Command) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        Write-Error "$Command is not installed or not in the PATH."
        exit 1
    }
}

Assert-Command "aws"

Write-Host "Packaging Ingestion Handler..."
$DistDir = ".\dist"
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }

# Create temporary directory for packaging
$TempDir = Join-Path $DistDir "temp_ingestion"
if (Test-Path $TempDir) { Remove-Item -Path $TempDir -Recurse -Force }
New-Item -ItemType Directory -Path $TempDir | Out-Null

# Copy source files
Copy-Item -Path ".\src\icpa" -Destination $TempDir -Recurse
Copy-Item -Path ".\src\icpa\ingestion\handlers.py" -Destination (Join-Path $TempDir "lambda_function.py")

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
Copy-Item -Path ".\src\icpa" -Destination $TempDir -Recurse
Copy-Item -Path ".\dist\lambda_packaging\orchestration\lambda_function.py" -Destination (Join-Path $TempDir "lambda_function.py")

# Zip it
$RouterZip = Join-Path $DistDir "router_lambda.zip"
if (Test-Path $RouterZip) { Remove-Item -Path $RouterZip -Force }
Compress-Archive -Path "$TempDir\*" -DestinationPath $RouterZip

# Cleanup
Remove-Item -Path $TempDir -Recurse -Force

Write-Host "Updating Lambda Code..."
aws lambda update-function-code --function-name ICPA-Ingestion-Handler --zip-file "fileb://$ZipFile" --profile $Profile --region $Region --no-cli-pager
aws lambda update-function-code --function-name ICPA-Textract-Result-Handler --zip-file "fileb://$ZipFile" --profile $Profile --region $Region --no-cli-pager
aws lambda update-function-code --function-name ICPA-Transcribe-PostProcess-Handler --zip-file "fileb://$ZipFile" --profile $Profile --region $Region --no-cli-pager
aws lambda update-function-code --function-name ICPA-Router-Lambda --zip-file "fileb://$RouterZip" --profile $Profile --region $Region --no-cli-pager
aws lambda update-function-code --function-name ICPA-Fraud-Agent-Lambda --zip-file "fileb://$RouterZip" --profile $Profile --region $Region --no-cli-pager
aws lambda update-function-code --function-name ICPA-Adjudication-Agent-Lambda --zip-file "fileb://$RouterZip" --profile $Profile --region $Region --no-cli-pager
aws lambda update-function-code --function-name ICPA-Summarization-Lambda --zip-file "fileb://$RouterZip" --profile $Profile --region $Region --no-cli-pager
aws lambda update-function-code --function-name ICPA-Notification-Lambda --zip-file "fileb://$RouterZip" --profile $Profile --region $Region --no-cli-pager

Write-Host "Code update complete. You may now run the upload test."
