# Phase 7: Quick Start Guide

## 🚀 5-Minute Deployment

### Step 1: Deploy Infrastructure (2 minutes)

```bash
# Navigate to infrastructure directory
cd infra

# Deploy the Analytics Stack
cdk deploy ICPA-AnalyticsStack

# Expected output:
# ✅ ICPA-AnalyticsStack
# 
# Outputs:
# ICPA-AnalyticsStack.AnalyticsBucketName = icpa-analytics-lake
# ICPA-AnalyticsStack.FirehoseStreamName = icpa-claims-analytics-stream
# ICPA-AnalyticsStack.GlueDatabaseName = icpa_analytics_db
# ICPA-AnalyticsStack.GlueCrawlerName = icpa-claims-analytics-crawler
# ICPA-AnalyticsStack.AthenaWorkgroupName = icpa-analytics-workgroup
```

### Step 2: Verify Deployment (1 minute)

```bash
# Run Phase 7 verification script
uv run scripts/verify_phase_7.py

# Expected results:
# ✓ S3 Analytics Bucket
# ✓ Kinesis Firehose Stream  
# ✓ DynamoDB Stream
# ✓ Stream Processor Lambda
# ✓ Glue Database
# ✓ Glue Crawler
# ✓ Athena Workgroup
```

### Step 3: Process Test Claims (2 minutes)

```bash
# Process a claim to populate the data lake
uv run scripts/verify_phase_6.py \
  --claim-id CLM-000001 \
  --api-url https://YOUR-API.execute-api.us-east-1.amazonaws.com/prod/ \
  --payout-override 849.52

# Wait 5-10 minutes for Firehose to deliver data
```

### Step 4: Run Glue Crawler (3 minutes)

```bash
# Start the Glue Crawler to index S3 data
uv run scripts/verify_phase_7.py --run-crawler

# Or manually:
aws glue start-crawler --name icpa-claims-analytics-crawler

# Check status:
aws glue get-crawler --name icpa-claims-analytics-crawler
```

### Step 5: Query with Athena (1 minute)

```bash
# Run a sample Athena query
uv run scripts/verify_phase_7.py --query-athena

# Expected output:
# ✓ Query completed successfully
#   Total Claims: 1
#   Unique Claims: 1
#   Avg Payout: £849.52
#   Total AWS Cost: £0.0012
```

---

## 📊 QuickSight Setup (15 minutes)

### Prerequisites
1. Enable QuickSight in your AWS account
2. Grant QuickSight access to:
   - S3 buckets: `icpa-analytics-lake`, `icpa-athena-query-results`
   - Athena workgroup: `icpa-analytics-workgroup`

### Step 1: Create Data Source (3 minutes)

1. Go to **QuickSight Console** → **Datasets** → **New dataset**
2. Choose **Athena**
3. Configure:
   - Data source name: `ICPA Analytics`
   - Athena workgroup: `icpa-analytics-workgroup`
4. Click **Create data source**

### Step 2: Import Dataset (3 minutes)

1. Select database: `icpa_analytics_db`
2. Select table: `claims`
3. Choose **Import to SPICE** (recommended)
4. Click **Edit/Preview data**

### Step 3: Add Calculated Fields (5 minutes)

```sql
-- Textract Savings
textract_savings = 
  ifelse(textract_operation = 'detect_text', 
    (0.0015 - 0.00015) * 1, 0)

-- AI Agreement Rate
ai_agreement_rate = 
  ifelse(ai_agreement_flag = 'AGREE', 1, 0)

-- Processing Time (minutes)
processing_time_minutes = 
  processing_duration_ms / 60000

-- Payout Variance
payout_variance = 
  payout_amount - ai_recommended_payout

-- Is Override
is_override = 
  ifelse(adjuster_override = true, 1, 0)
```

### Step 4: Create Dashboards (4 minutes per dashboard)

Follow the detailed guide: [docs/quicksight-dashboards.md](../docs/quicksight-dashboards.md)

#### Dashboard 1: Financial Operations (CFO View)
- Total Textract Savings (KPI)
- Total Payout Released (KPI)
- Average Cost per Claim (KPI)
- Monthly Payout Trend (Line Chart)
- Cost Breakdown (Pie Chart)

#### Dashboard 2: Model Performance (Data Science View)
- AI Agreement Rate (KPI)
- Override Rate (KPI)
- Fraud Score Heatmap (Heat Map)
- Override Justification Word Cloud

#### Dashboard 3: Operational Efficiency (Manager View)
- End-to-End Processing Time (KPI)
- Claims Processed Today (KPI)
- Throughput (KPI)
- Processing Time Trend (Line Chart)

---

## 🔍 Sample Athena Queries

### Financial Operations

```sql
-- Total Textract savings since launch
SELECT 
    SUM(CASE 
        WHEN textract_operation = 'detect_text' 
        THEN (0.0015 - 0.00015) 
        ELSE 0 
    END) AS total_textract_savings_gbp,
    COUNT(*) AS total_claims,
    AVG(total_aws_cost) AS avg_cost_per_claim
FROM icpa_analytics_db.claims
WHERE event_type = 'INSERT';
```

```sql
-- Monthly cost efficiency trend
SELECT 
    DATE_TRUNC('month', CAST(created_at AS TIMESTAMP)) AS month,
    COUNT(*) AS claims_processed,
    SUM(payout_amount) AS total_payout_gbp,
    SUM(total_aws_cost) AS total_aws_cost_gbp,
    (SUM(total_aws_cost) / SUM(payout_amount)) * 100 AS cost_percentage_of_payout
FROM icpa_analytics_db.claims
WHERE status = 'CLOSED_PAID'
GROUP BY DATE_TRUNC('month', CAST(created_at AS TIMESTAMP))
ORDER BY month DESC;
```

### Model Performance

```sql
-- Identify "Hard Cases" for prompt engineering
SELECT 
    claim_id,
    claimant_name,
    ai_recommended_payout,
    payout_amount,
    ABS(payout_amount - ai_recommended_payout) AS payout_difference,
    confidence_score,
    fraud_score,
    override_justification
FROM icpa_analytics_db.claims
WHERE adjuster_override = true
  AND ai_agreement_flag = 'DISAGREE'
  AND override_justification IS NOT NULL
ORDER BY ABS(payout_amount - ai_recommended_payout) DESC
LIMIT 50;
```

```sql
-- Weekly model performance tracking
SELECT 
    DATE_TRUNC('week', CAST(created_at AS TIMESTAMP)) AS week,
    COUNT(*) AS total_claims,
    SUM(CASE WHEN ai_agreement_flag = 'AGREE' THEN 1 ELSE 0 END) AS agreements,
    (SUM(CASE WHEN ai_agreement_flag = 'AGREE' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) AS agreement_rate,
    AVG(confidence_score) AS avg_confidence,
    AVG(fraud_score) AS avg_fraud_score
FROM icpa_analytics_db.claims
WHERE status = 'CLOSED_PAID'
GROUP BY DATE_TRUNC('week', CAST(created_at AS TIMESTAMP))
ORDER BY week DESC;
```

### Operational Efficiency

```sql
-- Bottleneck analysis (status transitions)
WITH status_transitions AS (
    SELECT 
        claim_id,
        status,
        CAST(updated_at AS TIMESTAMP) AS status_time,
        LAG(CAST(updated_at AS TIMESTAMP)) OVER (PARTITION BY claim_id ORDER BY updated_at) AS prev_status_time,
        LAG(status) OVER (PARTITION BY claim_id ORDER BY updated_at) AS prev_status
    FROM icpa_analytics_db.claims
    WHERE event_type = 'MODIFY'
)
SELECT 
    prev_status AS from_status,
    status AS to_status,
    COUNT(*) AS transitions,
    AVG(DATE_DIFF('second', prev_status_time, status_time)) AS avg_seconds,
    APPROX_PERCENTILE(DATE_DIFF('second', prev_status_time, status_time), 0.95) AS p95_seconds
FROM status_transitions
WHERE prev_status_time IS NOT NULL
GROUP BY prev_status, status
ORDER BY avg_seconds DESC;
```

```sql
-- Peak processing hours (capacity planning)
SELECT 
    EXTRACT(HOUR FROM CAST(created_at AS TIMESTAMP)) AS hour_of_day,
    EXTRACT(DOW FROM CAST(created_at AS TIMESTAMP)) AS day_of_week,
    COUNT(*) AS claims_submitted,
    AVG(processing_duration_ms / 60000) AS avg_processing_minutes
FROM icpa_analytics_db.claims
WHERE event_type = 'INSERT'
GROUP BY EXTRACT(HOUR FROM CAST(created_at AS TIMESTAMP)), 
         EXTRACT(DOW FROM CAST(created_at AS TIMESTAMP))
ORDER BY claims_submitted DESC;
```

---

## 🎯 Success Criteria Checklist

### Phase 7.1: Enable DB Streams ✅
- [ ] DynamoDB Stream enabled on `ICPA_Claims` table
- [ ] Lambda stream processor function deployed
- [ ] Kinesis Firehose delivery stream active
- [ ] S3 analytics bucket receiving `.parquet` files
- [ ] Files partitioned by `year/month/day`
- [ ] CloudWatch logs show successful deliveries

### Phase 7.2: Glue Crawler ✅
- [ ] Glue database `icpa_analytics_db` created
- [ ] Glue crawler `icpa-claims-analytics-crawler` configured
- [ ] Crawler successfully indexes S3 data
- [ ] Table `claims` visible in Glue Data Catalog
- [ ] Columns match analytics schema (20+ metrics)
- [ ] Partitions automatically discovered

### Phase 7.3: QuickSight Dashboard ✅
- [ ] Athena workgroup `icpa-analytics-workgroup` configured
- [ ] Sample queries return correct data
- [ ] QuickSight data source connected
- [ ] Dataset imported to SPICE
- [ ] Calculated fields created
- [ ] Three dashboards built (CFO, Data Science, Manager)
- [ ] Daily SPICE refresh scheduled
- [ ] Dashboards shared with stakeholders

---

## 🐛 Troubleshooting

### No data in analytics bucket
**Symptom**: S3 bucket is empty after processing claims

**Causes**:
1. Firehose buffering (5 min or 128 MB threshold)
2. Lambda stream processor errors
3. DynamoDB Stream not enabled

**Solutions**:
```bash
# Check Firehose status
aws firehose describe-delivery-stream --delivery-stream-name icpa-claims-analytics-stream

# Check Lambda logs
aws logs tail /aws/lambda/icpa-dynamodb-stream-processor --follow

# Verify DynamoDB Stream
aws dynamodb describe-table --table-name ICPA_Claims | grep -A 3 StreamSpecification
```

### Glue Crawler finds no tables
**Symptom**: Crawler runs successfully but creates no tables

**Causes**:
1. No Parquet files in S3 yet
2. Incorrect S3 path in crawler target
3. Parquet files corrupted

**Solutions**:
```bash
# Verify files exist
aws s3 ls s3://icpa-analytics-lake/claims/ --recursive

# Check crawler logs
aws glue get-crawler --name icpa-claims-analytics-crawler

# Re-run crawler
aws glue start-crawler --name icpa-claims-analytics-crawler
```

### Athena query returns empty results
**Symptom**: Query executes but returns 0 rows

**Causes**:
1. Glue Crawler hasn't indexed data yet
2. Partition pruning excludes all data
3. Wrong date format in WHERE clause

**Solutions**:
```sql
-- Check table schema
SHOW CREATE TABLE icpa_analytics_db.claims;

-- List partitions
SHOW PARTITIONS icpa_analytics_db.claims;

-- Query without filters first
SELECT COUNT(*) FROM icpa_analytics_db.claims;
```

### QuickSight can't access S3
**Symptom**: "Access Denied" when creating data source

**Causes**:
1. Missing IAM permissions for QuickSight
2. S3 bucket not granted to QuickSight service

**Solutions**:
1. Go to **QuickSight** → **Manage QuickSight** → **Security & permissions**
2. Click **Add or remove** under **QuickSight access to AWS services**
3. Select S3 buckets: `icpa-analytics-lake`, `icpa-athena-query-results`
4. Click **Update**

---

## 📈 Expected Metrics

### After Processing 100 Claims

| Metric | Expected Value |
|--------|---------------|
| **Total Textract Savings** | £0.15 - £0.20 |
| **Average Cost per Claim** | £0.40 - £0.50 |
| **AI Agreement Rate** | 85% - 95% |
| **Average Processing Time** | 3 - 7 minutes |
| **S3 Storage Used** | ~500 KB (Parquet) |
| **Athena Query Cost** | < $0.001 per query |

### After Processing 10,000 Claims

| Metric | Expected Value |
|--------|---------------|
| **Total Textract Savings** | £15 - £20 |
| **Total AWS Cost** | £4,000 - £5,000 |
| **Cost Percentage of Payout** | 0.5% - 1.0% |
| **S3 Storage Used** | ~50 MB (Parquet) |
| **Monthly Analytics Cost** | < $5 |

---

## 📚 Additional Resources

- **[Full Implementation Guide](../docs/phase-7-implementation.md)**
- **[QuickSight Dashboard Setup](../docs/quicksight-dashboards.md)**
- **[Architecture Decision Record](../docs/adr/adr-002-analytics-data-lake.md)**
- **[Verification Script](../scripts/verify_phase_7.py)**

---

**Need Help?**
- Slack: #icpa-dev
- Email: icpa-team@company.com
- Runbooks: [docs/runbooks/](../docs/runbooks/)
