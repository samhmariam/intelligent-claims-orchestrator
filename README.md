# Intelligent Claims Processing Agent (ICPA)

> **AI-native, event-driven claims orchestration using multi-agent patterns on AWS**

[![AWS](https://img.shields.io/badge/AWS-100%25-orange)](https://aws.amazon.com)
[![Bedrock](https://img.shields.io/badge/Amazon%20Bedrock-Enabled-blue)](https://aws.amazon.com/bedrock/)
[![Security](https://img.shields.io/badge/Security-HIPAA%20%7C%20GLBA-green)](docs/prd.md#79-compliance-mapping)

---

## Quick Start (5 Minutes)

### Prerequisites
- **AWS Account** with Bedrock access enabled in `us-east-1`
- **Python 3.13** (see `.python-version`)
- **AWS CLI v2** configured with credentials
- **AWS CDK v2** (for infrastructure)

### Local Setup
```bash
# Clone repository
git clone <repo-url>
cd intelligent-claims-orchestrator

# Install dependencies
pip install -r requirements.txt  # or use poetry/uv

# Configure AWS credentials
aws configure

# Run validation checks
python .agents/validate-state.py

# Sample claim data
# test-data/claims/CLM-000001/claim.json
```

---

## Architecture Overview

### System Design
ICPA implements a **serverless, event-driven architecture** with multi-agent orchestration:

```
┌─────────────────────────────────────────────────────────────────┐
│                         INGESTION LAYER                         │
│  API Gateway (Private) → Lambda → S3 (Raw Bucket)              │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PROCESSING LAYER                           │
│  Textract/Transcribe → Comprehend Medical (PHI) → Glue DQ      │
│  → S3 (Clean Bucket) | Quarantine Bucket                       │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION LAYER                          │
│  Step Functions State Machine                                   │
│  ├─ Summarization Agent                                         │
│  ├─ Router Agent                                                │
│  ├─ Fraud Detection Agent (Bedrock)                             │
│  ├─ Adjudication Agent (Bedrock)                                │
│  └─ Human-in-the-Loop (HITL) via SNS + API Gateway              │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                       PERSISTENCE LAYER                         │
│  DynamoDB (Claims, Steps, Idempotency, Evaluation)             │
│  S3 (Artifacts, Summaries, Logs)                               │
└─────────────────────────────────────────────────────────────────┘
```

**Key Principles:**
- **Private Subnets Only:** No NAT Gateways; all AWS API calls via VPC Endpoints
- **Canonical Schemas:** Strict contracts for Claim, Document, SourcePointer, AgentResult
- **Idempotency:** SHA256-based deduplication with 24-hour TTL
- **Observability:** CloudWatch + X-Ray tracing across all components

📖 **[Full PRD](docs/prd.md)** | **[Agent Coordination](docs/agent-coordination.md)**

---

## Development Workflow (SDLC Agents)

This repository uses **seven AI-native agents** aligned to SDLC phases:

| Phase | Agent | Role | Prompt Guide |
|-------|-------|------|--------------|
| **1. Plan** | Plan Agent | Product Manager (AWS-only) | [.agents/01-plan.md](.agents/01-plan.md) |
| **2. Design** | Design Agent | AI/ML Architect (AWS-only) | [.agents/02-design.md](.agents/02-design.md) |
| **3. Build** | Build Agent | Data Scientist (AWS-only) | [.agents/03-build.md](.agents/03-build.md) |
| **4. Test** | Test Agent | Security Engineer (AWS-only) | [.agents/04-test.md](.agents/04-test.md) |
| **5. Review** | Review Agent | Cloud Solutions Architect | [.agents/05-review.md](.agents/05-review.md) |
| **6. Document** | Document Agent | Compliance Officer (AWS-only) | [.agents/06-document.md](.agents/06-document.md) |
| **7. Deploy** | Deploy & Maintain Agent | DevOps Engineer (AWS-only) | [.agents/07-deploy-maintain.md](.agents/07-deploy-maintain.md) |

### Agent Handoff Flow
```
Plan → Design → Build → Test → Review → Document → Deploy
  ↓       ↓       ↓      ↓       ↓         ↓         ↓
Questions  Interfaces  Code  Coverage  Fixes   Runbooks  Monitoring
```

**State Coordination:** All agents share a canonical state contract ([docs/agent-coordination.md](docs/agent-coordination.md)). Validate handoffs with:
```bash
python .agents/validate-state.py --phase DESIGN --check-dependencies
```

---

## Security & Compliance

### Compliance Frameworks
- **HIPAA:** PHI detection via Comprehend Medical with >0.90 confidence threshold
- **GLBA:** Encryption at rest (KMS), in transit (TLS 1.2+), access logging (CloudTrail)

### Security Architecture
- **Network Isolation:** Private subnets, no internet access, VPC endpoints only
- **Least Privilege IAM:** Role-based access with `kms:ViaService` conditions
- **Data Quarantine:** Automatic isolation of PHI-detected documents
- **Audit Trail:** DynamoDB captures all workflow steps with timestamps

### Key Security Controls
| Control | Implementation | Validation |
|---------|---------------|------------|
| **Encryption at Rest** | S3 SSE-KMS, DynamoDB KMS | AWS Config rule |
| **Encryption in Transit** | TLS 1.2+ on ALB/API Gateway | Security scan |
| **IAM Policies** | Least privilege per Lambda | IAM Access Analyzer |
| **PHI Protection** | Comprehend Medical + Quarantine | Golden set tests |

📖 **[PRD Section 7: Security Requirements](docs/prd.md#7-operational-security--compliance-requirements)**

---

## Cost Model

### Target: **$0.45 per Claim** (Non-HITL Path, maximum)

| Service | Cost per Claim | Notes |
|---------|---------------|-------|
| **Lambda** | $0.08 | 6 invocations × 512MB × 3s avg |
| **Bedrock (Claude Sonnet)** | $0.25 | 2 agent calls × 5K tokens |
| **Textract** | $0.06 | 2 pages average per claim |
| **S3** | $0.02 | Storage + retrieval |
| **Step Functions** | $0.02 | State transitions |
| **DynamoDB** | $0.02 | Read/write units |
| **Total** | **$0.45** | |

### Cost Optimization Strategies
- **Model Tiering:** Route low-complexity claims to Claude Haiku ($0.08 vs $0.25)
- **Batch Processing:** Textract async API for multi-page PDFs
- **S3 Lifecycle:** Auto-delete raw bucket after 30 days
- **Reserved Capacity:** Consider Savings Plans for predictable workloads

📊 **[Cost Dashboard Spec](docs/prd.md#metrics-dashboard-specification)**

---

## Observability

### Key Metrics (SLIs)
- **Latency:** P95 end-to-end < 120s (non-HITL)
- **Accuracy:** DecisionAccuracy ≥ 90% on golden set
- **Availability:** 99.9% monthly for orchestration layer
- **Error Rate:** < 2% for workflow failures

### CloudWatch Dashboards
- **Claim Flow:** INTAKE → PROCESSING → APPROVED/DENIED (real-time)
- **Agent Performance:** Fraud/Adjudication latency P50/P95/P99
- **Cost Tracking:** Daily spend by AWS service
- **HITL Queue Depth:** Claims awaiting human review

### Alarms (Critical)
| Alarm | Threshold | Action |
|-------|-----------|--------|
| `WorkflowLatencyP95` | > 120s for 5 min | SNS → PagerDuty |
| `ErrorHandlingState` | > 2% in 15 min | Auto-rollback |
| `PHIQuarantineRate` | > 10% of claims | Security review |

📈 **[Observability Contract](docs/prd.md#76-observability-contract)**
📘 **[OpenTelemetry Guide](docs/observability/opentelemetry-guide.md)**

### ADOT Instrumentation (Finalized)
- ADOT Lambda layer attached to all Lambdas.
- Structured JSON logs include `trace_id`.
- Required span annotations: `claim_id`, `agent_type`, `model_id`, `decision`.

---

## Deployment (AWS-Only)

### Infrastructure
- Deploy stacks with AWS CDK from `infra/`.
- Example: `cd infra && cdk deploy ICPA-FoundationStack`

### Prompt Governance
- Seed prompts to SSM using [scripts/seed_prompts.py](scripts/seed_prompts.py).
- Use `/icpa/prompts/{agent_name}/v{MAJOR}.{MINOR}.{PATCH}` and update `latest` pointer.

### Validation
- Run gate checks in PRD Section 6 before staging/production.

---

## Analytics & Reporting (Phase 7)

### Data Lake Architecture
ICPA implements a **serverless, event-driven data lake** for real-time operational insights:

```
DynamoDB Claims Table
    ↓ (DynamoDB Streams)
Lambda Stream Processor
    ↓ (Transform & Batch)
Kinesis Data Firehose
    ↓ (Parquet Conversion)
S3 Analytics Lake
    ↓ (Scheduled Crawl)
AWS Glue Crawler
    ↓ (SQL Schema)
Amazon Athena
    ↓ (Visualizations)
Amazon QuickSight
```

### Three Dashboard Views

#### 1. Financial Operations (CFO View)
- **Total Textract Savings**: Track ~85% cost reduction from using `detect_text` vs. `analyze_document`
- **Total Payout Released**: Monitor GBP released via BACS vs. budget
- **Average Cost per Claim**: Target < £0.50 per claim
- **Monthly Payout Trend**: Visualize claim volume and payout patterns

#### 2. Model Performance (Data Science View)
- **AI Agreement Rate**: Track AI vs. human adjuster agreement (target ≥ 90%)
- **Override Rate**: Monitor frequency of human overrides
- **Fraud Score Heatmap**: Identify high-risk patterns by region/vehicle type
- **Override Justification Analysis**: Sentiment analysis to improve prompts

#### 3. Operational Efficiency (Manager View)
- **End-to-End Processing Time**: Monitor P95 latency (target < 5 minutes)
- **Claims Throughput**: Track claims processed per hour/day
- **Bottleneck Detection**: Identify slowest workflow stages
- **Hourly Volume Heatmap**: Capacity planning for peak hours

### Model Drift Feedback Loop
Weekly "Hard Case" reviews automatically identify disagreements between AI and human adjusters:
1. Query claims with `adjuster_override = true`
2. Extract common patterns from `override_justification`
3. Update Adjudication Agent prompts with new edge cases
4. A/B test improvements and measure agreement rate increase

### Cost: < $5/month (excluding QuickSight)
- **S3 Storage**: $0.001/month (with lifecycle policies)
- **Athena Queries**: $0.015/month (Parquet reduces scans by 80-95%)
- **Glue Crawler**: $0.18/month (runs every 6 hours)
- **Firehose**: $0.002/month (batched delivery)

📊 **[QuickSight Setup Guide](docs/quicksight-dashboards.md)**  
📖 **[Phase 7 Implementation](docs/phase-7-implementation.md)**  
🏛️ **[ADR-002: Analytics Data Lake](docs/adr/adr-002-analytics-data-lake.md)**

### Deployment
```bash
# Deploy Analytics Stack
cd infra
cdk deploy ICPA-AnalyticsStack

# Verify deployment
uv run scripts/verify_phase_7.py

# Run Glue Crawler (after processing some claims)
uv run scripts/verify_phase_7.py --run-crawler

# Query data with Athena
uv run scripts/verify_phase_7.py --query-athena
```

---

## Contact & Escalation

### Development Team
- **Product Owner:** [Name] (@handle)
- **Tech Lead:** [Name] (@handle)
- **Security DRI:** [Name] (@handle)

### Escalation Path
1. **P3 (Minor):** Slack #icpa-dev
2. **P2 (Major):** Slack #icpa-oncall + Email
3. **P1 (Critical):** PagerDuty → On-call engineer
4. **P0 (Outage):** PagerDuty → Manager + VP Engineering

### Support Channels
- **Slack:** #icpa-dev (development), #icpa-oncall (production)
- **Email:** icpa-team@company.com
- **Wiki:** [Confluence Page URL]
- **Runbooks:** [docs/runbooks/](docs/runbooks/)

---

## Testing

### Test Pyramid
- **Unit Tests (70%):** pytest for each Lambda function
- **Integration Tests (20%):** Step Functions with mocked Bedrock
- **E2E Tests (10%):** Full claim lifecycle on staging

### Verification Scripts
```bash
# Foundation checks
uv run scripts/verify_phase_0.py

# End-to-end HITL workflow (requires API URL)
python scripts/verify_phase_6.py --claim-id CLM-000001 --api-url https://<api-id>.execute-api.us-east-1.amazonaws.com/prod

# Analytics pipeline
uv run scripts/verify_phase_7.py
```

📋 **[Testing Strategy](docs/prd.md#testing-strategy)**

---

## Deployment

### Environments
- **Dev:** Auto-deploy on merge to `main` (us-east-1)
- **Staging:** Manual approval after E2E tests pass
- **Prod:** Blue/Green deployment with 10% canary for 1 hour

### Release Checklist
Before any production deploy:
- [ ] Golden Set DecisionAccuracy ≥ 90%
- [ ] Security scan (Checkov/Prowler) passing
- [ ] DR/HA drill completed within 30 days
- [ ] Cost budget approved by Finance
- [ ] Compliance sign-off (Legal/Privacy)
- [ ] Runbook tested in non-prod

📦 **[Deploy & Maintain Agent](.agents/07-deploy-maintain.md)**

---

## Documentation

### Key Documents
- **[PRD](docs/prd.md)** - Complete product requirements with canonical schemas
- **[Agent Coordination](docs/agent-coordination.md)** - State contract for SDLC agents
- **[Architecture Decision Records](docs/adr/)** - Major design decisions
- **[Runbooks](docs/runbooks/)** - Incident response procedures
- **[FAQ](docs/faq.md)** - Common questions and troubleshooting

### Code Examples
- **[Snippets](docs/snippets/)** - Reference implementations for each AWS service
- **[Test Data](test-data/)** - Sample claims and expected outputs

---

## Disaster Recovery

### Backup Strategy
- **S3 Versioning:** Enabled on clean/quarantine buckets
- **DynamoDB PITR:** Point-in-time recovery enabled (35-day retention)
- **CloudFormation Stacks:** Version-controlled in Git

### Recovery Targets
- **RPO (Recovery Point Objective):** ≤ 24 hours
- **RTO (Recovery Time Objective):** ≤ 4 hours

### DR Drill Schedule
Quarterly disaster recovery drills documented in `docs/incidents/dr-drill-YYYY-MM-DD.md`

---

## License

[Internal Use Only - Proprietary]

---

## Acknowledgments

Built with:
- **AWS Bedrock** (Claude 3 Sonnet)
- **AWS Step Functions** (Workflow orchestration)
- **Amazon Textract** (Document extraction)
- **Amazon Comprehend Medical** (PHI detection)

---

**Last Updated:** February 2, 2026  
**Version:** 1.0.0  
**Maintained by:** ICPA Engineering Team
