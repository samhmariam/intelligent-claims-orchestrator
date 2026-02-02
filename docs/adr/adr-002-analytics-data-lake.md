# ADR-002: Serverless Analytics Data Lake Architecture

## Status
**ACCEPTED** - February 1, 2026

## Context

The Intelligent Claims Processing Accelerator (ICPA) requires a comprehensive analytics and reporting solution to track:

1. **Financial Operations**: Cost savings (Textract optimization), payout tracking, budget adherence
2. **Model Performance**: AI vs. human agreement, model drift detection, fraud score accuracy
3. **Operational Efficiency**: End-to-end latency, throughput, bottleneck identification

### Requirements

- **No Impact on Production**: Analytics queries must NOT affect DynamoDB production performance
- **Real-Time Insights**: Data must be available within 5-10 minutes of claim processing
- **Low Cost**: Target < $10/month for 10,000 claims/month (excluding QuickSight licenses)
- **Scalability**: Must handle 100,000+ claims/month without architectural changes
- **Queryability**: Business users should be able to run ad-hoc SQL queries
- **Retention**: Keep raw data for 180 days, then archive to Glacier for compliance

### Constraints

- **Serverless Only**: No EC2 instances or RDS databases
- **AWS Native**: Prefer AWS services over third-party tools
- **Minimal Maintenance**: No manual ETL jobs or schema migrations
- **Cost Optimization**: Leverage Parquet, S3 lifecycle, and query optimization

## Decision

We will implement a **Serverless Event-Driven Data Lake** using:

1. **DynamoDB Streams**: Capture every INSERT/MODIFY on `ICPA_Claims` table
2. **AWS Lambda**: Transform stream events into analytics format
3. **Kinesis Data Firehose**: Batch and deliver to S3 with Parquet conversion
4. **S3**: Store analytics data in compressed, columnar format
5. **AWS Glue**: Catalog data for SQL queries
6. **Amazon Athena**: Provide SQL query engine
7. **Amazon QuickSight**: Deliver three dashboard views (CFO, Data Science, Manager)

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Production Claims Processing                     │
│                                                                       │
│  ┌──────────────┐       ┌──────────────┐       ┌──────────────┐   │
│  │   Textract   │──────>│ Step Function│──────>│  DynamoDB    │   │
│  └──────────────┘       └──────────────┘       │  ICPA_Claims │   │
│                                                  └───────┬──────┘   │
└──────────────────────────────────────────────────────────┼──────────┘
                                                            │
                                                            │ DynamoDB Streams
                                                            │ (NEW_AND_OLD_IMAGES)
                                                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Analytics Data Lake                            │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Lambda Stream Processor (icpa-dynamodb-stream-processor)     │  │
│  │  - Transforms DynamoDB records                                │  │
│  │  - Extracts financial, performance, operational metrics       │  │
│  │  - Batches up to 500 records                                  │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                                │                                     │
│                                │ PutRecordBatch                      │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Kinesis Data Firehose (icpa-claims-analytics-stream)         │  │
│  │  - Buffers 5 min OR 128 MB                                    │  │
│  │  - Converts JSON → Parquet (Snappy compression)               │  │
│  │  - Partitions by year/month/day                               │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                                │                                     │
│                                │ Parquet Files                       │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ S3 Analytics Lake (icpa-analytics-lake)                       │  │
│  │  - claims/year=2026/month=02/day=01/*.parquet                 │  │
│  │  - Lifecycle: Intelligent-Tiering (30d) → Glacier (180d)     │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                                │                                     │
│                                │ Scheduled Crawl (6hr)               │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ AWS Glue Crawler (icpa-claims-analytics-crawler)             │  │
│  │  - Discovers schema                                           │  │
│  │  - Indexes partitions                                         │  │
│  │  - Updates Glue Data Catalog                                  │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                                │                                     │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Glue Data Catalog (icpa_analytics_db.claims)                 │  │
│  │  - Table schema with 20+ metrics                              │  │
│  │  - Partition metadata                                         │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                                │                                     │
│                                │ SQL Queries                         │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Amazon Athena (icpa-analytics-workgroup)                     │  │
│  │  - Serverless SQL query engine                                │  │
│  │  - $5/TB scanned (Parquet = 80-95% savings)                   │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                                │                                     │
│                                │ SPICE Import                        │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Amazon QuickSight                                             │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │  │
│  │  │ CFO View     │  │ Data Science │  │ Manager View │       │  │
│  │  │ (Financial)  │  │ (Performance)│  │ (Operations) │       │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

## Alternatives Considered

### Alternative 1: Query DynamoDB Directly

**Approach**: Use DynamoDB query/scan operations for analytics

**Pros**:
- Simple: No additional infrastructure
- Real-time: Immediate consistency

**Cons**:
- ❌ **Performance Impact**: Analytics queries would consume read capacity
- ❌ **Cost**: DynamoDB reads are expensive at scale ($1.25/million reads)
- ❌ **Limited Query Capabilities**: No SQL, no JOIN, no aggregations

**Verdict**: ❌ **REJECTED** - Would degrade production performance

### Alternative 2: Stream to OpenSearch

**Approach**: DynamoDB Streams → Lambda → Amazon OpenSearch

**Pros**:
- Rich query capabilities (Lucene syntax)
- Good for log analysis and full-text search
- Built-in visualizations (Kibana)

**Cons**:
- ❌ **Cost**: $20-50/month for smallest cluster (t3.small.search)
- ❌ **Maintenance**: Requires cluster management, index optimization
- ❌ **Overkill**: We don't need full-text search or sub-second latency

**Verdict**: ❌ **REJECTED** - Too expensive for our use case

### Alternative 3: Stream to RDS/Aurora

**Approach**: DynamoDB Streams → Lambda → RDS PostgreSQL

**Pros**:
- Familiar SQL interface
- ACID transactions
- Good for complex JOINs

**Cons**:
- ❌ **Cost**: $15-30/month for smallest RDS instance (db.t3.micro)
- ❌ **Not Serverless**: Must pre-provision capacity
- ❌ **Maintenance**: Backups, patching, scaling

**Verdict**: ❌ **REJECTED** - Not serverless, higher cost

### Alternative 4: Kinesis Data Analytics

**Approach**: DynamoDB Streams → Kinesis Data Analytics → S3

**Pros**:
- Real-time aggregations
- Streaming SQL queries

**Cons**:
- ❌ **Complexity**: Requires writing SQL for transformations
- ❌ **Cost**: $0.11/hour per KPU (~$80/month minimum)
- ❌ **Overkill**: We don't need real-time aggregations

**Verdict**: ❌ **REJECTED** - Too expensive for batch analytics

### Alternative 5: AWS Data Pipeline

**Approach**: Scheduled EMR jobs to export DynamoDB → S3

**Pros**:
- Mature service
- Good for large batch exports

**Cons**:
- ❌ **Deprecated**: AWS recommends using Glue or Step Functions instead
- ❌ **Batch Only**: No real-time updates (12+ hour delay)
- ❌ **Complexity**: Requires managing EMR clusters

**Verdict**: ❌ **REJECTED** - Legacy service, not real-time

## Decision Rationale

### Why DynamoDB Streams?

1. **Zero Impact on Production**: Streams are asynchronous and don't affect table performance
2. **Built-In Change Data Capture (CDC)**: No custom polling logic required
3. **Guaranteed Ordering**: Events delivered in order per partition key
4. **24-Hour Retention**: Provides buffer for transient failures

### Why Kinesis Data Firehose?

1. **Serverless**: No infrastructure to manage
2. **Automatic Batching**: Optimizes S3 API calls (saves cost)
3. **Built-In Parquet Conversion**: No custom Lambda code for format transformation
4. **Error Handling**: Automatically retries failed deliveries, sends to error bucket

### Why Parquet Format?

1. **Compression**: 70-90% smaller than JSON (Snappy algorithm)
2. **Columnar Storage**: Athena only scans required columns (80-95% cost savings)
3. **Schema Evolution**: Can add columns without breaking existing queries
4. **Athena Native**: Optimal format for Amazon Athena

**Cost Example**:
- **JSON**: 10,000 claims × 5 KB = 50 MB/month → $0.023/month storage, $0.25/query (scan 50 MB)
- **Parquet**: 10,000 claims × 0.5 KB = 5 MB/month → $0.002/month storage, $0.025/query (scan 5 MB)
- **Savings**: 90% storage, 90% query cost

### Why AWS Glue Crawler?

1. **Automatic Schema Discovery**: No manual table definitions
2. **Partition Management**: Automatically detects year/month/day partitions
3. **Schema Evolution**: Updates table schema when new columns added
4. **Integration**: Native integration with Athena and QuickSight

### Why Amazon Athena?

1. **Serverless**: No infrastructure, pay-per-query
2. **SQL Standard**: Compatible with ANSI SQL, easy for business users
3. **Cost-Effective**: $5/TB scanned (Parquet makes this ~$0.25/TB)
4. **Federated Queries**: Can JOIN with other data sources if needed

### Why Amazon QuickSight?

1. **Native AWS Integration**: Works seamlessly with Athena
2. **SPICE Engine**: In-memory caching for sub-second dashboard loads
3. **Affordable**: $5/reader/month (vs. Tableau $70/user/month)
4. **Embedded Analytics**: Can embed dashboards in custom apps if needed

## Cost Analysis

### Baseline: 10,000 claims/month

| Component | Cost Formula | Monthly Cost |
|-----------|--------------|--------------|
| DynamoDB Streams | 10,000 read requests × $0.02/100K | $0.002 |
| Lambda Invocations | 100 invocations × $0.20/1M | $0.00002 |
| Lambda Duration | 100 × 100ms × 256MB × $0.0000166667/GB-s | $0.0004 |
| Kinesis Firehose | 50MB × $0.029/GB | $0.0015 |
| S3 Storage (30d) | 50MB × $0.023/GB | $0.0012 |
| S3 Storage (180d) | 50MB × 6 months × $0.004/GB (Glacier) | $0.012 |
| Glue Crawler | 4 runs/day × $0.44/hr × 0.1hr | $0.176 |
| Athena Queries | 10/day × 5MB × $5/TB | $0.0075 |
| **TOTAL** | | **< $5/month** |

**QuickSight** (separate):
- 3 authors × $24/month = $72/month
- 20 readers × $5/month = $100/month
- **Total QuickSight**: $172/month

### Scaling: 100,000 claims/month

| Component | Monthly Cost |
|-----------|--------------|
| DynamoDB Streams | $0.02 |
| Lambda | $0.04 |
| Firehose | $0.015 |
| S3 Storage | $0.50 |
| Glue Crawler | $0.18 |
| Athena | $0.08 |
| **TOTAL** | **< $10/month** |

**Key Insight**: Cost scales **sub-linearly** due to batching and compression.

## Implementation Plan

### Phase 7.1: Enable DB Streams & Firehose ✓

1. Add DynamoDB Stream to `ICPA_Claims` table
2. Create Lambda stream processor
3. Create Kinesis Firehose delivery stream with Parquet conversion
4. Create S3 analytics bucket with lifecycle rules
5. Verify data flow end-to-end

### Phase 7.2: Glue Crawler & Catalog ✓

1. Create Glue Database `icpa_analytics_db`
2. Create Glue Crawler to index S3 data
3. Schedule crawler to run every 6 hours
4. Verify table schema in Glue Data Catalog

### Phase 7.3: QuickSight Dashboards ✓

1. Create Athena workgroup for analytics queries
2. Grant QuickSight access to S3 and Athena
3. Create Athena data source in QuickSight
4. Import dataset from Glue table to SPICE
5. Build three dashboards:
   - **Financial Operations** (CFO View)
   - **Model Performance** (Data Science View)
   - **Operational Efficiency** (Manager View)
6. Schedule daily SPICE refresh
7. Share dashboards with stakeholders

## Success Metrics

### Technical Metrics

- **Data Latency**: < 10 minutes from claim update to S3 delivery
- **Query Performance**: < 5 seconds for dashboard refresh
- **Cost per Claim**: < $0.001 (excluding QuickSight)
- **Storage Compression**: > 70% vs. JSON
- **Athena Cost Savings**: > 80% vs. uncompressed

### Business Metrics

1. **Financial Operations**:
   - Track £X,XXX saved via Textract optimization
   - Monitor total payout vs. budget
   - Alert if cost per claim exceeds £0.50

2. **Model Performance**:
   - AI agreement rate ≥ 90%
   - Override rate trending downward
   - Weekly "Hard Case" reviews for prompt engineering

3. **Operational Efficiency**:
   - End-to-end processing time < 5 minutes
   - Identify bottlenecks (Textract vs. Review)
   - Capacity planning for peak hours

## Risks & Mitigations

### Risk 1: Firehose Delivery Delays

**Risk**: Buffering causes 5-10 minute delay

**Impact**: Medium - Dashboards not "truly real-time"

**Mitigation**:
- Set expectations: "Near real-time" (5-10 min latency is acceptable)
- Alternative: Reduce buffer to 60s / 5MB (increases cost 5x)

### Risk 2: Schema Changes Break Queries

**Risk**: New columns added to claims table

**Impact**: Low - Glue Crawler handles schema evolution

**Mitigation**:
- Use `SELECT *` sparingly in Athena
- Update QuickSight calculated fields when schema changes
- Monitor Glue Crawler logs for errors

### Risk 3: Athena Cost Overruns

**Risk**: Users run expensive queries (full table scans)

**Impact**: Medium - Could exceed $50/month

**Mitigation**:
- Set Athena workgroup cost limit: $100/month
- Use partitioning to limit scans (year/month/day)
- Educate users on Parquet column pruning
- Monitor top queries in CloudWatch

### Risk 4: QuickSight SPICE Capacity

**Risk**: Dataset exceeds 10 GB SPICE limit

**Impact**: Low - 10K claims/month = ~5 MB compressed

**Mitigation**:
- Use incremental SPICE refresh (only new data)
- Filter dataset by last 90 days
- Archive old data to Glacier (not in SPICE)

## Monitoring

### CloudWatch Alarms

1. **Firehose Delivery Failures**:
   - Metric: `DeliveryToS3.DataFreshness`
   - Threshold: > 600 seconds (10 min)
   - Action: SNS notification to DevOps

2. **Lambda Stream Processor Errors**:
   - Metric: `Errors`
   - Threshold: > 5 errors in 5 minutes
   - Action: SNS notification + automatic retry

3. **Model Drift Detection**:
   - Metric: Custom CloudWatch metric `AIAgreementRate`
   - Threshold: < 85%
   - Action: SNS notification to Data Science team

### Dashboard KPIs

- **AI Agreement Rate**: Green ≥ 90%, Yellow 85-90%, Red < 85%
- **Override Rate**: Green < 10%, Yellow 10-20%, Red > 20%
- **Processing Time**: Green < 5 min, Yellow 5-10 min, Red > 10 min
- **Cost per Claim**: Green < £0.50, Yellow £0.50-£1.00, Red > £1.00

## Future Enhancements

### Phase 8: Predictive Analytics (Proposed)

- **Use Case**: Predict claim approval probability before human review
- **Approach**: SageMaker Autopilot on historical "Hard Cases"
- **Cost**: ~$50/month for training + inference

### Phase 9: Real-Time Dashboards (Proposed)

- **Use Case**: Live monitoring of claims processing (< 1 second latency)
- **Approach**: DynamoDB Streams → Kinesis Data Analytics → QuickSight Streaming API
- **Cost**: ~$80/month for Kinesis Data Analytics

### Phase 10: Cross-Region Replication (Proposed)

- **Use Case**: Disaster recovery for analytics data
- **Approach**: S3 Cross-Region Replication to eu-west-2
- **Cost**: ~$10/month for replication

## Related ADRs

- **ADR-001**: Step Functions Orchestration (dependency: produces claims data)
- **ADR-003**: Model Drift Detection (proposed: uses analytics data)

## References

- [DynamoDB Streams Documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)
- [Kinesis Firehose Data Transformation](https://docs.aws.amazon.com/firehose/latest/dev/data-transformation.html)
- [Athena Performance Tuning](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning.html)
- [QuickSight Best Practices](https://docs.aws.amazon.com/quicksight/latest/user/best-practices.html)
- [Parquet Format Specification](https://parquet.apache.org/docs/)

---

**Decision Maker**: ICPA Engineering Team  
**Approval Date**: February 1, 2026  
**Review Date**: May 1, 2026 (after 3 months of operation)
