# Phase 7: QuickSight Dashboard Setup Guide

## Overview
This guide walks you through setting up three QuickSight dashboards for the Intelligent Claims Processing Accelerator (ICPA) analytics system.

## Prerequisites
1. Deploy the Analytics Stack: `cdk deploy ICPA-AnalyticsStack`
2. Run the Glue Crawler to catalog data: `aws glue start-crawler --name icpa-claims-analytics-crawler`
3. Enable QuickSight in your AWS account (if not already enabled)
4. Grant QuickSight access to S3 and Athena

---

## QuickSight Setup Steps

### Step 1: Grant QuickSight Permissions

1. Go to **QuickSight Console** → **Manage QuickSight** → **Security & permissions**
2. Click **Add or remove** under **QuickSight access to AWS services**
3. Enable:
   - **Amazon S3**: Select `icpa-analytics-lake` and `icpa-athena-query-results` buckets
   - **Amazon Athena**: Enable with the workgroup `icpa-analytics-workgroup`

### Step 2: Create Athena Data Source

1. In QuickSight, go to **Datasets** → **New dataset**
2. Choose **Athena**
3. Configure:
   - **Data source name**: `ICPA Analytics`
   - **Athena workgroup**: `icpa-analytics-workgroup`
4. Click **Validate connection** → **Create data source**

### Step 3: Create Dataset from Glue Table

1. Select database: `icpa_analytics_db`
2. Select table: `claims` (created by Glue Crawler)
3. Choose **Import to SPICE for quicker analytics** (recommended)
4. Click **Edit/Preview data** to configure fields

#### Field Configuration

Ensure these calculated fields are created:

```sql
-- Cost Savings vs. Traditional Textract
textract_savings = 
  ifelse(textract_operation = 'detect_text', 
    (0.0015 - 0.00015) * 1,  -- $0.0015 (analyze_document) - $0.00015 (detect_text)
    0)

-- AI-Human Agreement
ai_agreement_rate = 
  ifelse(ai_agreement_flag = 'AGREE', 1, 0)

-- Processing Time in Minutes
processing_time_minutes = 
  processing_duration_ms / 60000

-- Cost per Claim
cost_per_claim = 
  total_aws_cost

-- Payout Variance (AI vs Human decision)
payout_variance = 
  payout_amount - ai_recommended_payout

-- Is Override
is_override = 
  ifelse(adjuster_override = true, 1, 0)
```

---

## Dashboard 1: Financial Operations (CFO View)

### Key Metrics

1. **Total Textract Savings (YTD)**
   - Visual Type: KPI
   - Value: `SUM(textract_savings)`
   - Format: Currency (GBP)
   - Comparison: Previous period

2. **Total Payout Released**
   - Visual Type: KPI
   - Value: `SUM(payout_amount)`
   - Format: Currency (GBP)
   - Comparison: Budget target

3. **Average Cost per Claim**
   - Visual Type: KPI
   - Value: `AVG(cost_per_claim)`
   - Format: Currency (GBP)
   - Target: £0.50 per claim

4. **Monthly Payout Trend**
   - Visual Type: Line Chart
   - X-axis: `created_at` (Month)
   - Y-axis: `SUM(payout_amount)`
   - Color: `status`
   - Filter: `status = 'CLOSED_PAID'`

5. **Cost Breakdown by Service**
   - Visual Type: Pie Chart
   - Slices:
     - `SUM(textract_cost)` as "Textract"
     - `SUM(bedrock_cost)` as "Bedrock"
   - Format: Currency (GBP)

6. **Textract Savings vs. Traditional**
   - Visual Type: Bar Chart
   - X-axis: `textract_operation`
   - Y-axis: `SUM(textract_savings)`
   - Color: `textract_operation`

### SQL Queries for Athena (Ad-hoc Analysis)

```sql
-- Total Textract savings since system launch
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

-- Cost per claim percentile analysis
SELECT 
    APPROX_PERCENTILE(total_aws_cost, 0.5) AS median_cost,
    APPROX_PERCENTILE(total_aws_cost, 0.95) AS p95_cost,
    APPROX_PERCENTILE(total_aws_cost, 0.99) AS p99_cost,
    MAX(total_aws_cost) AS max_cost
FROM icpa_analytics_db.claims
WHERE total_aws_cost > 0;
```

---

## Dashboard 2: Model Performance (Data Science View)

### Key Metrics

1. **AI Agreement Rate**
   - Visual Type: KPI
   - Value: `AVG(ai_agreement_rate) * 100`
   - Format: Percentage
   - Target: ≥ 90%

2. **Override Rate**
   - Visual Type: KPI
   - Value: `AVG(is_override) * 100`
   - Format: Percentage
   - Trend: Lower is better

3. **Average Fraud Score**
   - Visual Type: Gauge
   - Value: `AVG(fraud_score)`
   - Range: 0-100
   - Color: Green (0-30), Yellow (30-70), Red (70-100)

4. **AI vs. Human Agreement Over Time**
   - Visual Type: Line Chart
   - X-axis: `created_at` (Week)
   - Y-axis: `AVG(ai_agreement_rate) * 100`
   - Goal line: 90%

5. **Payout Variance Distribution**
   - Visual Type: Histogram
   - X-axis: `payout_variance` (bins of £50)
   - Y-axis: Count
   - Color: `ai_agreement_flag`

6. **Override Justification Word Cloud**
   - Visual Type: Word Cloud
   - Words: `override_justification`
   - Size: Frequency
   - Filter: `adjuster_override = true`

7. **Fraud Score Heatmap by Vehicle Type**
   - Visual Type: Heat Map
   - Rows: `vehicle_type`
   - Columns: `region`
   - Values: `AVG(fraud_score)`
   - Color: Red gradient (higher = more suspicious)

8. **Confidence Score vs. Override Correlation**
   - Visual Type: Scatter Plot
   - X-axis: `confidence_score`
   - Y-axis: `is_override`
   - Color: `fraud_score`

### SQL Queries for Athena (Model Drift Analysis)

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

-- Override sentiment analysis (top reasons)
SELECT 
    override_justification,
    COUNT(*) AS frequency,
    AVG(payout_amount - ai_recommended_payout) AS avg_payout_adjustment,
    AVG(fraud_score) AS avg_fraud_score
FROM icpa_analytics_db.claims
WHERE adjuster_override = true
  AND override_justification IS NOT NULL
GROUP BY override_justification
ORDER BY frequency DESC
LIMIT 20;

-- Fraud score accuracy (do high fraud scores correlate with overrides?)
SELECT 
    CASE 
        WHEN fraud_score < 30 THEN 'Low Risk'
        WHEN fraud_score < 70 THEN 'Medium Risk'
        ELSE 'High Risk'
    END AS risk_category,
    COUNT(*) AS claims,
    SUM(CASE WHEN adjuster_override = true THEN 1 ELSE 0 END) AS overrides,
    (SUM(CASE WHEN adjuster_override = true THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) AS override_rate
FROM icpa_analytics_db.claims
WHERE status = 'CLOSED_PAID'
GROUP BY CASE 
        WHEN fraud_score < 30 THEN 'Low Risk'
        WHEN fraud_score < 70 THEN 'Medium Risk'
        ELSE 'High Risk'
    END
ORDER BY override_rate DESC;
```

---

## Dashboard 3: Operational Efficiency (Manager View)

### Key Metrics

1. **End-to-End Processing Time**
   - Visual Type: KPI
   - Value: `AVG(processing_time_minutes)`
   - Format: Minutes
   - Target: < 5 minutes

2. **Claims Processed Today**
   - Visual Type: KPI
   - Value: `COUNT(claim_id)`
   - Filter: `created_at = TODAY()`
   - Comparison: Yesterday

3. **Throughput (Claims/Hour)**
   - Visual Type: KPI
   - Value: `COUNT(claim_id) / HOURS_BETWEEN(MIN(created_at), MAX(created_at))`
   - Filter: Last 24 hours

4. **Processing Time Trend**
   - Visual Type: Line Chart
   - X-axis: `created_at` (Hour)
   - Y-axis: `AVG(processing_time_minutes)`
   - Filter: Last 7 days

5. **Claims by Status**
   - Visual Type: Donut Chart
   - Slices: `status`
   - Values: `COUNT(claim_id)`

6. **Processing Time Percentiles**
   - Visual Type: Box Plot
   - Y-axis: `processing_time_minutes`
   - Outliers: Highlight claims > P95

7. **Bottleneck Detection (by Phase)**
   - Visual Type: Funnel Chart
   - Stages:
     - SUBMITTED → PROCESSING_TEXTRACT
     - PROCESSING_TEXTRACT → PROCESSING_ASSEMBLER
     - PROCESSING_ASSEMBLER → PENDING_HUMAN_REVIEW
     - PENDING_HUMAN_REVIEW → CLOSED_PAID
   - Values: Average duration for each transition

8. **Hourly Claim Volume Heatmap**
   - Visual Type: Heat Map
   - Rows: Day of week
   - Columns: Hour of day
   - Values: `COUNT(claim_id)`
   - Color: Blue gradient

### SQL Queries for Athena (Bottleneck Analysis)

```sql
-- Average processing time by status transition
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

-- Claims stuck in PENDING_HUMAN_REVIEW (SLA breach detection)
SELECT 
    claim_id,
    claimant_name,
    status,
    created_at,
    updated_at,
    DATE_DIFF('hour', CAST(updated_at AS TIMESTAMP), CURRENT_TIMESTAMP) AS hours_in_status
FROM icpa_analytics_db.claims
WHERE status = 'PENDING_HUMAN_REVIEW'
  AND DATE_DIFF('hour', CAST(updated_at AS TIMESTAMP), CURRENT_TIMESTAMP) > 24
ORDER BY hours_in_status DESC;

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

-- Throughput by day (last 30 days)
SELECT 
    DATE_TRUNC('day', CAST(created_at AS TIMESTAMP)) AS day,
    COUNT(*) AS claims_processed,
    AVG(processing_duration_ms / 60000) AS avg_processing_minutes,
    MAX(processing_duration_ms / 60000) AS max_processing_minutes
FROM icpa_analytics_db.claims
WHERE event_type = 'INSERT'
  AND CAST(created_at AS TIMESTAMP) > CURRENT_TIMESTAMP - INTERVAL '30' DAY
GROUP BY DATE_TRUNC('day', CAST(created_at AS TIMESTAMP))
ORDER BY day DESC;
```

---

## Step 4: Schedule Dashboard Refresh

1. In QuickSight, go to **Datasets** → Select `ICPA Analytics`
2. Click **Schedule refresh**
3. Configure:
   - **Frequency**: Daily at 6:00 AM UTC
   - **Time zone**: UTC
   - **Refresh type**: Full refresh
4. Click **Create**

---

## Step 5: Share Dashboards

1. Go to **Dashboards** → Select dashboard → **Share**
2. Add users/groups with appropriate permissions:
   - **CFO View**: Finance team (Viewer)
   - **Data Science View**: ML Engineers (Viewer/Editor)
   - **Manager View**: Operations managers (Viewer)

---

## Model Drift Feedback Loop

### Automated Prompt Improvement Process

1. **Weekly Hard Case Review**:
   ```sql
   SELECT * FROM icpa_analytics_db.claims
   WHERE adjuster_override = true
     AND CAST(created_at AS TIMESTAMP) > CURRENT_TIMESTAMP - INTERVAL '7' DAY
   ORDER BY ABS(payout_amount - ai_recommended_payout) DESC;
   ```

2. **Extract Common Patterns**:
   - Group by `override_justification` keywords
   - Identify edge cases (e.g., "pre-existing damage", "policy exclusion")

3. **Update Adjudication Agent Prompt**:
   - Add new examples to system prompt in [src/icpa/bedrock/agents/adjudication_agent.py](../src/icpa/bedrock/agents/adjudication_agent.py)
   - Example:
     ```python
     EDGE_CASE_EXAMPLES = """
     Case: Pre-existing damage mentioned in claim notes
     Action: Reduce payout by 30% and flag for further investigation
     
     Case: Policy exclusion for modified vehicles
     Action: Deny claim if vehicle modifications are documented
     """
     ```

4. **A/B Test**:
   - Deploy updated prompt to 10% of claims
   - Monitor `ai_agreement_rate` improvement
   - Roll out to 100% if agreement rate increases

5. **Continuous Monitoring**:
   - Set CloudWatch alarm if `ai_agreement_rate` drops below 85%
   - Trigger automated review of recent overrides

---

## Cost Optimization

### Storage Costs
- **S3 Analytics Lake**: ~$0.023/GB/month (Standard) → $0.004/GB/month (Intelligent-Tiering after 30 days)
- **Parquet Compression**: Typically 70-90% smaller than JSON
- **Example**: 10,000 claims/month × 5KB/claim = 50MB/month → **$0.001/month**

### Query Costs
- **Athena**: $5 per TB scanned
- **Parquet + Partitioning**: Reduces scan volume by 80-95%
- **Example**: 10 queries/day × 10MB scanned = 3GB/month → **$0.015/month**

### Total Monthly Cost (10K claims/month)
- Storage: $0.001
- Athena: $0.015
- Glue Crawler: $0.44 (hourly crawls)
- Firehose: $0.029 per GB ingested
- **Total: < $5/month** (excluding QuickSight license)

---

## Troubleshooting

### Issue: Glue Crawler finds no data
- **Cause**: Firehose hasn't delivered any files yet (5-minute buffer)
- **Solution**: Wait 5-10 minutes after deploying, then run crawler

### Issue: QuickSight can't access S3
- **Cause**: Missing IAM permissions
- **Solution**: Re-run **Step 1** and explicitly grant S3 bucket access

### Issue: Athena query fails with "Table not found"
- **Cause**: Crawler hasn't run yet
- **Solution**: Manually start crawler: `aws glue start-crawler --name icpa-claims-analytics-crawler`

### Issue: SPICE refresh fails
- **Cause**: Large dataset exceeds SPICE capacity (10GB default)
- **Solution**: Use incremental refresh or filter data by date range

---

## Next Steps

1. **Deploy Analytics Stack**: `cdk deploy ICPA-AnalyticsStack`
2. **Wait for Data**: Process 10-20 claims to populate the data lake
3. **Run Glue Crawler**: `aws glue start-crawler --name icpa-claims-analytics-crawler`
4. **Create QuickSight Dashboards**: Follow this guide
5. **Set Up Alerts**: Configure CloudWatch alarms for model drift
6. **Schedule Weekly Reviews**: Review "Hard Cases" to improve prompts

---

## References

- [AWS Glue Crawler Documentation](https://docs.aws.amazon.com/glue/latest/dg/add-crawler.html)
- [Amazon Athena Best Practices](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning.html)
- [QuickSight Calculated Fields Guide](https://docs.aws.amazon.com/quicksight/latest/user/calculated-fields.html)
- [Parquet Performance Optimization](https://docs.aws.amazon.com/athena/latest/ug/columnar-storage.html)
