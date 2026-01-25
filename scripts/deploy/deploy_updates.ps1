param (
    [string]$Profile = "my-dev",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

$LambdaExecutionRoleName = "ICPA-Lambda-Execution-Role"
$RepoRootPath = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$PolicyDir = Join-Path $RepoRootPath "infra\\policies"
$EventbridgeDir = Join-Path $RepoRootPath "infra\\eventbridge"
if (-not (Test-Path $PolicyDir)) { New-Item -ItemType Directory -Path $PolicyDir -Force | Out-Null }
if (-not (Test-Path $EventbridgeDir)) { New-Item -ItemType Directory -Path $EventbridgeDir -Force | Out-Null }

function Assert-Command ($Command) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        Write-Error "$Command is not installed or not in the PATH."
        exit 1
    }
}

Assert-Command "aws"

Write-Host "Using AWS Profile: $Profile"
Write-Host "Using Region: $Region"

Write-Host "Getting Account ID..."
try {
    $Identity = aws sts get-caller-identity --profile $Profile --output json --no-cli-pager | ConvertFrom-Json
    $AccountId = $Identity.Account
    Write-Host "Account ID: $AccountId"
}
catch {
    Write-Error "Failed to get identity. Please check your credentials for profile '$Profile'."
    exit 1
}

# Helper to get absolute file URI
function Get-FileUri ($FileName) {
    $AbsPath = (Resolve-Path $FileName).Path
    return "file://$AbsPath"
}

function Ensure-LambdaFunction ($FuncName, $Handler, $RoleArn, $ZipPath, $Vars) {
    $Exists = $false
    aws lambda get-function --function-name $FuncName --profile $Profile --region $Region --no-cli-pager 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $Exists = $true
    }

    if (-not $Exists) {
        if (-not (Test-Path $ZipPath)) {
            Write-Error "Lambda package not found at $ZipPath. Run update_code.ps1 first."
            exit 1
        }
        Write-Host "Creating Lambda $FuncName..."
        aws lambda create-function `
            --function-name $FuncName `
            --runtime python3.11 `
            --handler $Handler `
            --role $RoleArn `
            --zip-file "fileb://$ZipPath" `
            --timeout 30 `
            --profile $Profile `
            --region $Region `
            --no-cli-pager | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create $FuncName. Ensure the IAM role exists and the zip package is valid."
            exit 1
        }
    }

    if ($Vars -and (Get-Command aws -ErrorAction SilentlyContinue)) {
        Update-LambdaConfigSafe $FuncName $Vars
    }
}

# --- 1. Textract Configuration ---
Write-Host "`n--- Configuring Textract Dependencies ---"

# Create SNS Topic
Write-Host "Ensuring SNS Topic exists..."
$TopicArn = (aws sns create-topic --name ICPA-Textract-Completion-Topic --profile $Profile --region $Region --output text --query TopicArn --no-cli-pager)
if ([string]::IsNullOrWhiteSpace($TopicArn)) { Write-Error "Failed to get TopicArn"; exit 1 }
Write-Host "Topic ARN: $TopicArn"

# Create Textract Role
Write-Host "Ensuring Textract Role exists..."
$TrustPolicy = @{
    Version   = "2012-10-17"
    Statement = @(
        @{
            Effect    = "Allow"
            Principal = @{ Service = "textract.amazonaws.com" }
            Action    = "sts:AssumeRole"
        }
    )
} | ConvertTo-Json -Depth 5 -Compress
$TrustPolicyFile = Join-Path $PolicyDir "textract-trust.json"
$TrustPolicy | Out-File -FilePath $TrustPolicyFile -Encoding ascii
$TrustPolicyUri = Get-FileUri $TrustPolicyFile

$RoleArn = ""
try {
    $RoleArn = (aws iam create-role --role-name ICPA-Textract-Publish-Role --assume-role-policy-document $TrustPolicyUri --profile $Profile --region $Region --output text --query Role.Arn --no-cli-pager 2>$null)
}
catch {
    # If role exists (or creation failed), try to get existing
    Write-Host "Role creation might have failed (exists?), trying to get existing role..."
}

if ([string]::IsNullOrWhiteSpace($RoleArn)) {
    $RoleArn = (aws iam get-role --role-name ICPA-Textract-Publish-Role --profile $Profile --region $Region --output text --query Role.Arn --no-cli-pager)
}

if ([string]::IsNullOrWhiteSpace($RoleArn)) { Write-Error "Failed to get Textract Role ARN"; exit 1 }
Write-Host "Role ARN: $RoleArn"

# Attach Policy
aws iam attach-role-policy --role-name ICPA-Textract-Publish-Role --policy-arn arn:aws:iam::aws:policy/AmazonSNSFullAccess --profile $Profile --region $Region --no-cli-pager

# --- 2. Update Lambda Environment ---
Write-Host "`n--- Updating Lambda Environment Variables ---"

# Hardcoded Table Names (from verified config)
$DynamoVars = @{
    CLAIMS_TABLE      = "icpa-storage-ICPAClaims-14RV6A78Q2Q3E"
    IDEMPOTENCY_TABLE = "icpa-storage-ICPAIdempotency-19C4TKOU5P46H"
    EVALUATION_TABLE  = "icpa-storage-ICPAEvaluation-1W1B5YTU48OFA"
}

# Add Textract Vars
$TextractVars = $DynamoVars.Clone()
$TextractVars["TEXTRACT_ROLE_ARN"] = $RoleArn
$TextractVars["TEXTRACT_SNS_TOPIC_ARN"] = $TopicArn
# Default buckets
$TextractVars["RAW_BUCKET"] = "icpa-storage-rawbucket-5pyjjk0wlvsc"
$TextractVars["CLEAN_BUCKET"] = "icpa-storage-cleanbucket-a8ijbh8ladxx"
$TextractVars["QUARANTINE_BUCKET"] = "icpa-storage-quarantinebucket-3eveuiovfjsl"


function Update-LambdaConfig ($FuncName, $Vars) {
    Write-Host "Updating $FuncName..."
    
    # Construct Environment string properly
    $EnvString = "Variables={"
    foreach ($key in $Vars.Keys) {
        $EnvString += "$key=$($Vars[$key]),"
    }
    $EnvString = $EnvString.TrimEnd(",") + "}"
    
    aws lambda update-function-configuration --function-name $FuncName --environment $EnvString --profile $Profile --region $Region --no-cli-pager
}

# Update Ingestion
Update-LambdaConfig "ICPA-Ingestion-Handler" $TextractVars

# Update Textract Result Handler
Update-LambdaConfig "ICPA-Textract-Result-Handler" $TextractVars

# Update Transcribe Handler
Update-LambdaConfig "ICPA-Transcribe-PostProcess-Handler" $TextractVars

# Update Summarization
$SumVars = @{ CLEAN_BUCKET = "icpa-storage-cleanbucket-a8ijbh8ladxx" } # And Dynamo vars
foreach ($k in $DynamoVars.Keys) { $SumVars[$k] = $DynamoVars[$k] }
Update-LambdaConfig "ICPA-Summarization-Lambda" $SumVars

# Update Router
Update-LambdaConfig "ICPA-Router-Lambda" $DynamoVars

# Update Agents
function Update-LambdaConfigSafe ($FuncName, $NewVars) {
    Write-Host "Updating $FuncName safely..."
    $ConfigJson = aws lambda get-function-configuration --function-name $FuncName --profile $Profile --region $Region --output json --no-cli-pager 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Skipping $FuncName (function not found)."
        return
    }
    $Config = $ConfigJson | ConvertFrom-Json
    $CurrentVars = @{}
    if ($Config.Environment -and $Config.Environment.Variables) {
        $Config.Environment.Variables.PSObject.Properties | ForEach-Object {
            $CurrentVars[$_.Name] = $_.Value
        }
    }
    
    foreach ($key in $NewVars.Keys) {
        $CurrentVars[$key] = $NewVars[$key]
    }
    
    $EnvString = "Variables={"
    foreach ($key in $CurrentVars.Keys) {
        $EnvString += "$key=$($CurrentVars[$key]),"
    }
    $EnvString = $EnvString.TrimEnd(",") + "}"
    
    aws lambda update-function-configuration --function-name $FuncName --environment $EnvString --profile $Profile --region $Region --no-cli-pager
}

Update-LambdaConfigSafe "ICPA-Fraud-Agent-Lambda" $DynamoVars
Update-LambdaConfigSafe "ICPA-Adjudication-Agent-Lambda" $DynamoVars
Update-LambdaConfigSafe "ICPA-Notification-Lambda" $DynamoVars

# Ensure new terminal-state and HITL callback Lambdas exist
$LambdaExecutionRoleArn = (aws iam get-role --role-name $LambdaExecutionRoleName --profile $Profile --region $Region --output text --query Role.Arn --no-cli-pager)
$OrchestrationZip = Join-Path $RepoRootPath "dist\\router_lambda.zip"
Ensure-LambdaFunction "ICPA-Terminal-State-Lambda" "lambda_function.terminal_state_handler" $LambdaExecutionRoleArn $OrchestrationZip $DynamoVars
Ensure-LambdaFunction "ICPA-HITL-Callback-Lambda" "lambda_function.hitl_callback_handler" $LambdaExecutionRoleArn $OrchestrationZip @{}

# --- 2d. Increase timeouts for agent wrapper Lambdas ---
Write-Host "`n--- Updating Agent Wrapper Timeouts ---"
aws lambda update-function-configuration --function-name "ICPA-Fraud-Agent-Lambda" --timeout 60 --profile $Profile --region $Region --no-cli-pager
aws lambda update-function-configuration --function-name "ICPA-Adjudication-Agent-Lambda" --timeout 60 --profile $Profile --region $Region --no-cli-pager

# --- 2b. IAM Permissions for SSM Prompt/Model Reads ---
Write-Host "`n--- Ensuring Lambda SSM Read Permissions ---"
$SsmPolicy = @{
    Version   = "2012-10-17"
    Statement = @(
        @{
            Effect   = "Allow"
            Action   = @(
                "ssm:GetParameter",
                "ssm:GetParameters",
                "ssm:GetParametersByPath"
            )
            Resource = @(
                "arn:aws:ssm:$Region`:$AccountId`:parameter/icpa/prompts/*",
                "arn:aws:ssm:$Region`:$AccountId`:parameter/icpa/models/*"
            )
        }
    )
} | ConvertTo-Json -Depth 5 -Compress
$SsmPolicyFile = Join-Path $PolicyDir "lambda-ssm-read-policy.json"
$SsmPolicy | Out-File -FilePath $SsmPolicyFile -Encoding ascii
$SsmPolicyUri = Get-FileUri $SsmPolicyFile

aws iam put-role-policy --role-name $LambdaExecutionRoleName --policy-name ICPA-Lambda-SSM-Read --policy-document $SsmPolicyUri --profile $Profile --region $Region --no-cli-pager

# --- 2c. IAM Permissions for Bedrock Agent Invocation ---
Write-Host "`n--- Ensuring Lambda Bedrock Invoke Permissions ---"
$BedrockPolicy = @{
    Version   = "2012-10-17"
    Statement = @(
        @{
            Effect   = "Allow"
            Action   = @(
                "bedrock:InvokeAgent",
                "bedrock:InvokeModel"
            )
            Resource = "*"
        }
    )
} | ConvertTo-Json -Depth 5 -Compress
$BedrockPolicyFile = Join-Path $PolicyDir "lambda-bedrock-invoke-policy.json"
$BedrockPolicy | Out-File -FilePath $BedrockPolicyFile -Encoding ascii
$BedrockPolicyUri = Get-FileUri $BedrockPolicyFile

aws iam put-role-policy --role-name $LambdaExecutionRoleName --policy-name ICPA-Lambda-Bedrock-Invoke --policy-document $BedrockPolicyUri --profile $Profile --region $Region --no-cli-pager

# --- 2e. IAM Permissions for SNS Publish (HITL notifications) ---
Write-Host "`n--- Ensuring Lambda SNS Publish Permissions ---"
$SnsPolicy = @{
    Version   = "2012-10-17"
    Statement = @(
        @{
            Effect   = "Allow"
            Action   = @(
                "sns:Publish"
            )
            Resource = @(
                "arn:aws:sns:$Region`:$AccountId`:ICPA-Human-Review-Topic"
            )
        }
    )
} | ConvertTo-Json -Depth 5 -Compress
$SnsPolicyFile = Join-Path $PolicyDir "lambda-sns-publish-policy.json"
$SnsPolicy | Out-File -FilePath $SnsPolicyFile -Encoding ascii
$SnsPolicyUri = Get-FileUri $SnsPolicyFile

aws iam put-role-policy --role-name $LambdaExecutionRoleName --policy-name ICPA-Lambda-SNS-Publish --policy-document $SnsPolicyUri --profile $Profile --region $Region --no-cli-pager

# --- 2f. IAM Permissions for Step Functions task callbacks ---
Write-Host "`n--- Ensuring Lambda Step Functions Callback Permissions ---"
$SfnPolicy = @{
    Version   = "2012-10-17"
    Statement = @(
        @{
            Effect   = "Allow"
            Action   = @(
                "states:SendTaskSuccess",
                "states:SendTaskFailure"
            )
            Resource = "*"
        }
    )
} | ConvertTo-Json -Depth 5 -Compress
$SfnPolicyFile = Join-Path $PolicyDir "lambda-sfn-callback-policy.json"
$SfnPolicy | Out-File -FilePath $SfnPolicyFile -Encoding ascii
$SfnPolicyUri = Get-FileUri $SfnPolicyFile

aws iam put-role-policy --role-name $LambdaExecutionRoleName --policy-name ICPA-Lambda-StepFunctions-Callback --policy-document $SfnPolicyUri --profile $Profile --region $Region --no-cli-pager

# Quick verification: inline policies + role boundary
Write-Host "`n--- Verifying Lambda Role Policies ---"
try {
    $RoleInfo = aws iam get-role --role-name $LambdaExecutionRoleName --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
    if ($RoleInfo.Role.PermissionsBoundary) {
        Write-Host "Permissions boundary ARN: $($RoleInfo.Role.PermissionsBoundary.PermissionsBoundaryArn)"
    }
    else {
        Write-Host "Permissions boundary ARN: <none>"
    }

    $InlinePolicies = aws iam list-role-policies --role-name $LambdaExecutionRoleName --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
    Write-Host "Inline policies: $($InlinePolicies.PolicyNames -join ', ')"
    if ($InlinePolicies.PolicyNames -contains "ICPA-Lambda-Bedrock-Invoke") {
        $PolicyDoc = aws iam get-role-policy --role-name $LambdaExecutionRoleName --policy-name "ICPA-Lambda-Bedrock-Invoke" --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
        Write-Host "ICPA-Lambda-Bedrock-Invoke policy document:"
        $PolicyDoc.PolicyDocument | ConvertTo-Json -Depth 10
    }
}
catch {
    Write-Warning "Failed to verify Lambda role policies: $_"
}

# Quick verification: SCP effective policy (only if org is available)
Write-Host "`n--- Verifying SCP Effective Policy ---"
try {
    $OrgInfo = aws organizations describe-organization --profile $Profile --output json --no-cli-pager | ConvertFrom-Json
    if ($OrgInfo.Organization -and $OrgInfo.Organization.Id) {
        $ScpPolicy = aws organizations describe-effective-policy --policy-type SERVICE_CONTROL_POLICY --target-id $AccountId --profile $Profile --output json --no-cli-pager | ConvertFrom-Json
        if ($ScpPolicy.EffectivePolicy -and $ScpPolicy.EffectivePolicy.PolicyContent) {
            Write-Host "Effective SCP policy content:"
            $ScpPolicy.EffectivePolicy.PolicyContent
        }
        else {
            Write-Host "No effective SCP policy content returned."
        }
    }
    else {
        Write-Host "Organization not detected; skipping SCP check."
    }
}
catch {
    Write-Warning "Failed to verify organization/SCP policy: $_"
}

# Quick verification: Bedrock agent alias, agent role, and model configuration
Write-Host "`n--- Verifying Bedrock Agent Configuration ---"
try {
    $FraudConfig = aws lambda get-function-configuration --function-name "ICPA-Fraud-Agent-Lambda" --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
    $FraudVars = $FraudConfig.Environment.Variables
    $AgentId = $FraudVars.BEDROCK_AGENT_ID
    $AgentAliasId = $FraudVars.BEDROCK_AGENT_ALIAS_ID
    if ($AgentId -and $AgentAliasId) {
        Write-Host "Bedrock agent ID: $AgentId"
        Write-Host "Bedrock agent alias ID: $AgentAliasId"

        $AliasInfo = aws bedrock-agent get-agent-alias --agent-id $AgentId --agent-alias-id $AgentAliasId --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
        if ($AliasInfo.agentAlias -and $AliasInfo.agentAlias.agentAliasArn) {
            Write-Host "Agent alias ARN: $($AliasInfo.agentAlias.agentAliasArn)"
        }

        $AgentInfo = aws bedrock-agent get-agent --agent-id $AgentId --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
        if ($AgentInfo.agent) {
            Write-Host "Agent ARN: $($AgentInfo.agent.agentArn)"
            Write-Host "Agent role ARN: $($AgentInfo.agent.agentResourceRoleArn)"
            Write-Host "Foundation model: $($AgentInfo.agent.foundationModel)"

            # Agent role policy inspection
            $AgentRoleArn = $AgentInfo.agent.agentResourceRoleArn
            $AgentRoleName = $AgentRoleArn.Split("/")[-1]
            Write-Host "Agent role name: $AgentRoleName"
            try {
                $AgentInline = aws iam list-role-policies --role-name $AgentRoleName --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
                Write-Host "Agent inline policies: $($AgentInline.PolicyNames -join ', ')"
                foreach ($policyName in $AgentInline.PolicyNames) {
                    $PolicyDoc = aws iam get-role-policy --role-name $AgentRoleName --policy-name $policyName --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
                    Write-Host "Agent inline policy $policyName document:"
                    $PolicyDoc.PolicyDocument | ConvertTo-Json -Depth 10
                }
            }
            catch {
                Write-Warning "Failed to list agent inline policies: $_"
            }
            try {
                $AgentAttached = aws iam list-attached-role-policies --role-name $AgentRoleName --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
                Write-Host "Agent attached policies: $($AgentAttached.AttachedPolicies.PolicyName -join ', ')"
            }
            catch {
                Write-Warning "Failed to list agent attached policies: $_"
            }
        }
    }
    else {
        Write-Host "Bedrock agent env vars not found on ICPA-Fraud-Agent-Lambda."
    }
}
catch {
    Write-Warning "Failed to verify Bedrock agent configuration: $_"
}

# Quick verification: Bedrock foundation model access
Write-Host "`n--- Verifying Bedrock Foundation Model Access ---"
try {
    $Models = aws bedrock list-foundation-models --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
    Write-Host "Foundation models visible: $($Models.modelSummaries.Count)"
    if ($AgentInfo -and $AgentInfo.agent -and $AgentInfo.agent.foundationModel) {
        $ModelId = $AgentInfo.agent.foundationModel
        Write-Host "Checking model access for: $ModelId"
        $ModelInfo = aws bedrock get-foundation-model --model-id $ModelId --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
        if ($ModelInfo -and $ModelInfo.modelDetails) {
            Write-Host "Model status: $($ModelInfo.modelDetails.modelLifecycle.status)"
        }
    }
}
catch {
    Write-Warning "Failed to verify Bedrock model access: $_"
}

# Ensure agent service role can invoke the configured foundation model
Write-Host "`n--- Ensuring Bedrock Agent Role InvokeModel Permissions ---"
try {
    $FraudConfig = aws lambda get-function-configuration --function-name "ICPA-Fraud-Agent-Lambda" --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
    $FraudVars = $FraudConfig.Environment.Variables
    $AgentId = $FraudVars.BEDROCK_AGENT_ID
    if ($AgentId) {
        $AgentInfo = aws bedrock-agent get-agent --agent-id $AgentId --profile $Profile --region $Region --output json --no-cli-pager | ConvertFrom-Json
        if ($AgentInfo.agent) {
            $AgentRoleArn = $AgentInfo.agent.agentResourceRoleArn
            $AgentRoleName = $AgentRoleArn.Split("/")[-1]
            $ModelId = $AgentInfo.agent.foundationModel
            Write-Host "Updating agent role: $AgentRoleName"
            Write-Host "Foundation model: $ModelId"

            $ModelArn = "arn:aws:bedrock:$Region`::foundation-model/$ModelId"
            $AgentInvokePolicy = @{
                Version   = "2012-10-17"
                Statement = @(
                    @{
                        Effect   = "Allow"
                        Action   = @(
                            "bedrock:InvokeModel",
                            "bedrock:InvokeModelWithResponseStream"
                        )
                        Resource = @($ModelArn)
                    }
                )
            } | ConvertTo-Json -Depth 5 -Compress
            $AgentInvokePolicyFile = Join-Path $PolicyDir "bedrock-agent-invoke-model-policy.json"
            $AgentInvokePolicy | Out-File -FilePath $AgentInvokePolicyFile -Encoding ascii
            $AgentInvokePolicyUri = Get-FileUri $AgentInvokePolicyFile

            aws iam put-role-policy --role-name $AgentRoleName --policy-name ICPA-Bedrock-Agent-InvokeModel --policy-document $AgentInvokePolicyUri --profile $Profile --region $Region --no-cli-pager
        }
        else {
            Write-Host "Bedrock agent not found; skipping agent role update."
        }
    }
    else {
        Write-Host "BEDROCK_AGENT_ID not found; skipping agent role update."
    }
}
catch {
    Write-Warning "Failed to update Bedrock agent role permissions: $_"
}


# --- 3. Textract Subscription ---
Write-Host "`n--- Configuring Textract SNS Subscription ---"
aws sns subscribe --topic-arn $TopicArn --protocol lambda --notification-endpoint "arn:aws:lambda:$Region`:$AccountId`:function:ICPA-Textract-Result-Handler" --profile $Profile --region $Region --no-cli-pager

try {
    aws lambda add-permission --function-name ICPA-Textract-Result-Handler --statement-id sns-textract-trigger --action "lambda:InvokeFunction" --principal sns.amazonaws.com --source-arn $TopicArn --profile $Profile --region $Region --no-cli-pager
}
catch {
    Write-Host "Permission might already exist or failed: $_"
}


# --- 4. EventBridge Configuration ---
Write-Host "`n--- Configuring EventBridge ---"

# Role
$EventRoleTrust = @{
    Version   = "2012-10-17"
    Statement = @(
        @{
            Effect    = "Allow"
            Principal = @{ Service = "events.amazonaws.com" }
            Action    = "sts:AssumeRole"
        }
    )
} | ConvertTo-Json -Depth 5 -Compress
$EventTrustFile = Join-Path $PolicyDir "eventbridge-trust.json"
$EventRoleTrust | Out-File -FilePath $EventTrustFile -Encoding ascii
$EventTrustUri = Get-FileUri $EventTrustFile

$EventRoleArn = ""
try {
    $EventRoleArn = (aws iam create-role --role-name ICPA-EventBridge-Execution-Role --assume-role-policy-document $EventTrustUri --profile $Profile --region $Region --output text --query Role.Arn --no-cli-pager 2>$null)
}
catch {
    # Try getting existing
}

if ([string]::IsNullOrWhiteSpace($EventRoleArn)) {
    $EventRoleArn = (aws iam get-role --role-name ICPA-EventBridge-Execution-Role --profile $Profile --region $Region --output text --query Role.Arn --no-cli-pager)
}

if ([string]::IsNullOrWhiteSpace($EventRoleArn)) { Write-Error "Failed to get EventBridge Role ARN"; exit 1 }

aws iam attach-role-policy --role-name ICPA-EventBridge-Execution-Role --policy-arn arn:aws:iam::aws:policy/AWSStepFunctionsFullAccess --profile $Profile --region $Region --no-cli-pager

# Rule
$EventPattern = @{
    source        = @("com.icpa.ingestion")
    "detail-type" = @("com.icpa.orchestration.start")
} | ConvertTo-Json -Depth 5 -Compress
$EventPatternFile = Join-Path $EventbridgeDir "event_pattern.json"
$EventPattern | Out-File -FilePath $EventPatternFile -Encoding ascii
$EventPatternUri = Get-FileUri $EventPatternFile

aws events put-rule --name ICPA-Start-Orchestration-Rule --event-pattern $EventPatternUri --profile $Profile --region $Region --no-cli-pager

# Target
$StateMachineArn = "arn:aws:states:$Region`:$AccountId`:stateMachine:ICPA-Claim-Orchestration"

# Ensure it's treated as an array for sure
$TargetObj = @{
    Id      = "1"
    Arn     = $StateMachineArn
    RoleArn = $EventRoleArn
}
$TargetsJson = "[$($TargetObj | ConvertTo-Json -Depth 5 -Compress)]"
$TargetsFile = Join-Path $EventbridgeDir "targets.json"
$TargetsJson | Out-File -FilePath $TargetsFile -Encoding ascii
$TargetsUri = Get-FileUri $TargetsFile

aws events put-targets --rule ICPA-Start-Orchestration-Rule --targets $TargetsUri --profile $Profile --region $Region --no-cli-pager

Write-Host "`n--- Configuration Update Complete! ---"
