param (
    [string]$Profile = "my-dev"
)

$ErrorActionPreference = "Stop"

$RawBucket = "icpa-storage-rawbucket-5pyjjk0wlvsc" 
$TestDataDir = ".\test-data\claims"

Write-Host "Checking for test data in $TestDataDir..."
if (-not (Test-Path $TestDataDir)) {
    Write-Warning "Test data directory not found. Generating sample data..."
    uv run -m src.data_generator.generator --n 1 --out ./test-data
}

# Find the first generated claim folder
$ClaimDir = Get-ChildItem -Path $TestDataDir -Directory | Select-Object -First 1

if ($ClaimDir) {
    $ClaimId = $ClaimDir.Name
    Write-Host "Uploading data for Claim: $ClaimId to bucket: $RawBucket"

    function Upload-File {
        param ($Path, $Key, $DocType)
        Write-Host "Uploading $Path to $Key (Type: $DocType)..."
        aws s3 cp $Path "s3://$RawBucket/$Key" --metadata "doc_type=$DocType,channel=web" --profile $Profile --no-cli-pager
    }

    # Upload Helper
    function Try-Upload ($FileName, $DocType) {
        $File = Get-Item (Join-Path $ClaimDir.FullName "raw\documents\$FileName") -ErrorAction SilentlyContinue
        if ($File -and $File.Length -gt 0) {
            Upload-File -Path $File.FullName -Key "$ClaimId/$FileName" -DocType $DocType
        }
    }

    Try-Upload "FNOL.pdf" "FNOL_FORM"
    Try-Upload "POLICE_REPORT.pdf" "POLICE_REPORT"
    Try-Upload "REPAIR_ESTIMATE.pdf" "ESTIMATE"
    Try-Upload "INVOICE.pdf" "INVOICE"
    Try-Upload "ADJUSTER_NOTES.pdf" "ADJUSTER_NOTES"

    # Upload Photos
    $Photos = Get-ChildItem -Path (Join-Path $ClaimDir.FullName "raw\photos") -Filter "*.jpg"
    foreach ($Photo in $Photos) {
        Upload-File -Path $Photo.FullName -Key "$ClaimId/photos/$($Photo.Name)" -DocType "DAMAGE_PHOTO"
    }

    Write-Host "`nUpload complete."
}
else {
    Write-Error "No claim data found even after generation attempt."
}
