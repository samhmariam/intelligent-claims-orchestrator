# Phase 7 Deployment Checklist

## Pre-Deployment

### Prerequisites Verification
- [ ] Phase 0-6 deployed successfully
- [ ] DynamoDB table `ICPA_Claims` exists and is operational
- [ ] AWS CLI configured with appropriate credentials
- [ ] CDK v2 installed (`cdk --version`)
- [ ] Python dependencies installed (`uv` or `pip`)

### Environment Check
```bash
# Verify AWS credentials
aws sts get-caller-identity

# Verify region
aws configure get region
# Expected: us-east-1

# Check existing stacks
cdk list
# Expected: ICPA-FoundationStack, ICPA-ApiStack
```

---

## Deployment Steps

### Step 1: Infrastructure Deployment

```bash
# Navigate to infrastructure directory
cd infra

# Synthesize CloudFormation template
cdk synth ICPA-AnalyticsStack

# Review changes
cdk diff ICPA-AnalyticsStack

# Deploy (with confirmation)
cdk deploy ICPA-AnalyticsStack

# Expected duration: 3-5 minutes
```

#### Deployment Checklist
- [ ] CloudFormation stack created successfully
- [ ] No errors in CloudFormation events
- [ ] All outputs displayed:
  - [ ] AnalyticsBucketName
  - [ ] FirehoseStreamName
  - [ ] GlueDatabaseName
  - [ ] GlueCrawlerName
  - [ ] AthenaWorkgroupName
  - [ ] AthenaResultsBucket

### Step 2: Verification

```bash
# Run Phase 7 verification script
uv run scripts/verify_phase_7.py
```

#### Verification Checklist
- [ ] ✓ S3 Analytics Bucket
- [ ] ✓ Kinesis Firehose Stream (status: ACTIVE)
- [ ] ✓ DynamoDB Stream (enabled on ICPA_Claims)
- [ ] ✓ Stream Processor Lambda (exists and connected)
- [ ] ✓ Glue Database (icpa_analytics_db)
- [ ] ✓ Glue Crawler (configured)
- [ ] ✓ Athena Workgroup (icpa-analytics-workgroup)
- [ ] ✓ Data Flow (claims → S3)

---

## Post-Deployment

### Step 3: Process Test Claims

```bash
# Process a few claims to populate the data lake
for i in {1..5}; do
  uv run scripts/verify_phase_6.py \
    --claim-id CLM-00000$i \
    --api-url https://YOUR-API-URL.execute-api.us-east-1.amazonaws.com/prod/ \
    --payout-override $((800 + RANDOM % 200))
done
```

#### Test Claims Checklist
- [ ] 5+ claims processed successfully
- [ ] Claims visible in DynamoDB table
- [ ] Wait 5-10 minutes for Firehose buffering

### Step 4: Run Glue Crawler

```bash
# Start the Glue Crawler
uv run scripts/verify_phase_7.py --run-crawler

# Or manually:
aws glue start-crawler --name icpa-claims-analytics-crawler

# Monitor crawler status
watch -n 5 'aws glue get-crawler --name icpa-claims-analytics-crawler --query "Crawler.State" --output text'
# Expected: RUNNING → STOPPING → READY (2-5 minutes)
```

#### Crawler Checklist
- [ ] Crawler started successfully
- [ ] Crawler completed without errors
- [ ] Table `claims` created in `icpa_analytics_db`
- [ ] Partitions discovered (year/month/day)
- [ ] Columns match schema (20+ fields)

### Step 5: Query with Athena

```bash
# Run sample Athena query
uv run scripts/verify_phase_7.py --query-athena
```

#### Athena Checklist
- [ ] Query executed successfully
- [ ] Results match processed claims
- [ ] Total claims count correct
- [ ] Payout amounts correct
- [ ] AWS costs calculated

---

## QuickSight Setup (Optional)

### Step 6: Enable QuickSight

**If QuickSight is already enabled in your account**, skip to Step 7.

```bash
# Check if QuickSight is enabled
aws quicksight describe-account-settings --aws-account-id $(aws sts get-caller-identity --query Account --output text) --region us-east-1
```

**If not enabled:**
1. Go to [QuickSight Console](https://us-east-1.quicksight.aws.amazon.com/)
2. Click **Sign up for QuickSight**
3. Choose **Enterprise** edition (30-day free trial)
4. Configure:
   - IAM role: Create new
   - S3 buckets: Select `icpa-analytics-lake` and `icpa-athena-query-results`
   - Athena: Enable access
5. Complete setup

#### QuickSight Checklist
- [ ] QuickSight account created
- [ ] IAM role has S3 and Athena permissions
- [ ] Can access QuickSight console

### Step 7: Create Data Source

Follow the guide: [docs/quicksight-dashboards.md](../docs/quicksight-dashboards.md)

1. Go to **QuickSight** → **Datasets** → **New dataset**
2. Choose **Athena**
3. Configure:
   - Data source name: `ICPA Analytics`
   - Athena workgroup: `icpa-analytics-workgroup`
4. Select database: `icpa_analytics_db`
5. Select table: `claims`
6. Import to SPICE

#### Data Source Checklist
- [ ] Athena data source created
- [ ] Dataset imported to SPICE
- [ ] Preview shows claim data
- [ ] Calculated fields added (5 fields)

### Step 8: Build Dashboards

Create three dashboards following the guide:

1. **Financial Operations (CFO View)**
   - [ ] Total Textract Savings (KPI)
   - [ ] Total Payout Released (KPI)
   - [ ] Average Cost per Claim (KPI)
   - [ ] Monthly Payout Trend (Line Chart)
   - [ ] Cost Breakdown (Pie Chart)

2. **Model Performance (Data Science View)**
   - [ ] AI Agreement Rate (KPI)
   - [ ] Override Rate (KPI)
   - [ ] Fraud Score Heatmap
   - [ ] Override Justification Word Cloud

3. **Operational Efficiency (Manager View)**
   - [ ] End-to-End Processing Time (KPI)
   - [ ] Claims Processed Today (KPI)
   - [ ] Throughput (KPI)
   - [ ] Processing Time Trend (Line Chart)

#### Dashboard Checklist
- [ ] 3 dashboards created
- [ ] All visuals render correctly
- [ ] SPICE refresh scheduled (daily at 6 AM UTC)
- [ ] Dashboards shared with stakeholders

---

## Validation

### Step 9: End-to-End Test

```bash
# Process a claim and verify it appears in analytics
CLAIM_ID="CLM-TEST-$(date +%s)"
echo "Processing claim: $CLAIM_ID"

# 1. Submit claim
uv run scripts/verify_phase_6.py \
  --claim-id $CLAIM_ID \
  --api-url https://YOUR-API-URL.execute-api.us-east-1.amazonaws.com/prod/ \
  --payout-override 999.99

# 2. Wait for Firehose delivery (5-10 minutes)
echo "Waiting 10 minutes for Firehose delivery..."
sleep 600

# 3. Verify in S3
aws s3 ls s3://icpa-analytics-lake/claims/ --recursive | grep $(date +%Y/%m/%d)

# 4. Run crawler
aws glue start-crawler --name icpa-claims-analytics-crawler

# 5. Wait for crawler
echo "Waiting 3 minutes for crawler..."
sleep 180

# 6. Query in Athena
aws athena start-query-execution \
  --query-string "SELECT * FROM icpa_analytics_db.claims WHERE claim_id = '$CLAIM_ID'" \
  --query-execution-context Database=icpa_analytics_db \
  --work-group icpa-analytics-workgroup \
  --result-configuration OutputLocation=s3://icpa-athena-query-results/
```

#### End-to-End Checklist
- [ ] Claim processed in DynamoDB
- [ ] Event captured by DynamoDB Stream
- [ ] Lambda processed event successfully
- [ ] Firehose delivered to S3
- [ ] Glue Crawler indexed data
- [ ] Athena query returned claim
- [ ] Total latency < 15 minutes

---

## Monitoring Setup

### Step 10: CloudWatch Alarms

```bash
# Create alarm for Model Drift (AI Agreement Rate < 85%)
aws cloudwatch put-metric-alarm \
  --alarm-name ICPA-AI-Agreement-Rate-Low \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 1 \
  --metric-name AIAgreementRate \
  --namespace ICPA/Analytics \
  --period 86400 \
  --statistic Average \
  --threshold 85 \
  --alarm-description "Alert when AI agreement rate drops below 85%" \
  --alarm-actions arn:aws:sns:us-east-1:YOUR-ACCOUNT-ID:icpa-alerts

# Create alarm for Firehose Delivery Failures
aws cloudwatch put-metric-alarm \
  --alarm-name ICPA-Firehose-Delivery-Failures \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --metric-name DeliveryToS3.Records \
  --namespace AWS/Firehose \
  --dimensions Name=DeliveryStreamName,Value=icpa-claims-analytics-stream \
  --period 300 \
  --statistic Sum \
  --threshold 10 \
  --alarm-description "Alert on Firehose delivery failures"

# Create alarm for Lambda Stream Processor Errors
aws cloudwatch put-metric-alarm \
  --alarm-name ICPA-Stream-Processor-Errors \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --dimensions Name=FunctionName,Value=icpa-dynamodb-stream-processor \
  --period 300 \
  --statistic Sum \
  --threshold 5 \
  --alarm-description "Alert on Lambda stream processor errors"
```

#### Monitoring Checklist
- [ ] CloudWatch alarms created
- [ ] SNS topic configured for alerts
- [ ] Email subscriptions confirmed
- [ ] Test alarms triggered successfully

---

## Documentation

### Step 11: Update Internal Wiki

- [ ] Add link to Phase 7 documentation
- [ ] Update architecture diagrams
- [ ] Share QuickSight dashboard URLs
- [ ] Document access procedures for new team members

### Step 12: Training

- [ ] Schedule walkthrough for Finance team (CFO Dashboard)
- [ ] Schedule walkthrough for Data Science team (Performance Dashboard)
- [ ] Schedule walkthrough for Operations team (Efficiency Dashboard)
- [ ] Create video tutorial for QuickSight usage

---

## Rollback Plan

### If Deployment Fails

```bash
# Option 1: Delete CloudFormation stack
aws cloudformation delete-stack --stack-name ICPA-AnalyticsStack

# Option 2: Use CDK destroy
cd infra
cdk destroy ICPA-AnalyticsStack

# Verify deletion
aws cloudformation describe-stacks --stack-name ICPA-AnalyticsStack
# Expected: Stack not found
```

### If Data Flow Issues

```bash
# Disable DynamoDB Stream (temporarily)
aws dynamodb update-table \
  --table-name ICPA_Claims \
  --stream-specification StreamEnabled=false

# Disable Lambda event source mapping
aws lambda list-event-source-mappings \
  --function-name icpa-dynamodb-stream-processor \
  --query "EventSourceMappings[0].UUID" \
  --output text | \
xargs -I {} aws lambda update-event-source-mapping --uuid {} --enabled false

# Re-enable after fixing issues
```

---

## Success Criteria

### Technical Success
- [ ] All infrastructure deployed without errors
- [ ] All verification tests pass
- [ ] End-to-end data flow working
- [ ] Athena queries return correct data
- [ ] QuickSight dashboards rendering

### Business Success
- [ ] Finance team can track Textract savings
- [ ] Data Science team can monitor AI performance
- [ ] Operations team can identify bottlenecks
- [ ] Weekly "Hard Case" review process established

### Cost Success
- [ ] Monthly analytics cost < $10 (excluding QuickSight)
- [ ] No unexpected CloudWatch charges
- [ ] S3 lifecycle policies active
- [ ] Athena query costs within budget

---

## Sign-Off

### Deployment Team

- [ ] **DevOps Engineer**: Infrastructure deployed and verified
  - Name: ________________
  - Date: ________________

- [ ] **Data Engineer**: Data flow validated
  - Name: ________________
  - Date: ________________

- [ ] **Security Engineer**: Permissions reviewed
  - Name: ________________
  - Date: ________________

### Stakeholders

- [ ] **Product Owner**: Acceptance criteria met
  - Name: ________________
  - Date: ________________

- [ ] **Tech Lead**: Code review completed
  - Name: ________________
  - Date: ________________

---

## Post-Deployment Review (1 Week)

Schedule a review meeting 1 week after deployment to assess:
- [ ] Data quality and completeness
- [ ] Dashboard adoption by stakeholders
- [ ] Any performance issues
- [ ] Cost vs. budget
- [ ] Feedback from end users

**Meeting Date**: ________________  
**Attendees**: ________________

---

## Additional Resources

- **[Implementation Guide](../docs/phase-7-implementation.md)**
- **[Quick Start Guide](../docs/phase-7-quick-start.md)**
- **[QuickSight Setup](../docs/quicksight-dashboards.md)**
- **[ADR-002](../docs/adr/adr-002-analytics-data-lake.md)**
- **[Verification Script](../scripts/verify_phase_7.py)**

---

**Checklist Version**: 1.0  
**Last Updated**: February 1, 2026  
**Maintained By**: ICPA Engineering Team
