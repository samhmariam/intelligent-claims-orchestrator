# Agent Coordination State (AWS-Only)

## Purpose
Define a shared, deterministic state contract that all seven agents use to coordinate handoffs across the SDLC phases for this AWS-only GenAI application.

## Canonical State (JSON)
```json
{
  "run_id": "UUID",
  "claim_id": "UUID [optional]",
  "phase": "Enum [PLAN, DESIGN, BUILD, TEST, REVIEW, DOCUMENT, DEPLOY_MAINTAIN]",
  "owner_agent": "Enum [PLAN, DESIGN, BUILD, TEST, REVIEW, DOCUMENT, DEPLOY_MAINTAIN]",
  "status": "Enum [NOT_STARTED, IN_PROGRESS, BLOCKED, COMPLETED]",
  "inputs": {
    "requirements_refs": ["String"],
    "design_refs": ["String"],
    "code_refs": ["String"],
    "test_refs": ["String"],
    "doc_refs": ["String"],
    "runbook_refs": ["String"]
  },
  "outputs": {
    "artifacts": [
      {
        "type": "Enum [PLAN, DESIGN, CODE, TEST, REVIEW, DOC, RUNBOOK]",
        "path": "String",
        "summary": "String"
      }
    ],
    "decisions": [
      {
        "title": "String",
        "rationale": "String",
        "owner": "String",
        "timestamp": "ISO-8601"
      }
    ]
  },
  "dependencies": [
    {
      "from_phase": "Enum [PLAN, DESIGN, BUILD, TEST, REVIEW, DOCUMENT, DEPLOY_MAINTAIN]",
      "to_phase": "Enum [PLAN, DESIGN, BUILD, TEST, REVIEW, DOCUMENT, DEPLOY_MAINTAIN]",
      "status": "Enum [OPEN, SATISFIED]",
      "note": "String"
    }
  ],
  "risks": [
    {
      "id": "String",
      "description": "String",
      "severity": "Enum [LOW, MEDIUM, HIGH]",
      "mitigation": "String"
    }
  ],
  "open_questions": [
    {
      "question": "String",
      "owner": "String",
      "status": "Enum [OPEN, ANSWERED]"
    }
  ],
  "aws_constraints": {
    "aws_only": true,
    "no_other_clouds": true,
    "regions": ["us-east-1"],
    "network": "Private subnets, no NAT, VPC endpoints"
  }
}
```

## Phase Handoff Requirements
Each agent MUST update the state before handing off to the next phase:

- **PLAN → DESIGN**
  - `inputs.requirements_refs` set
  - `open_questions` captured
  - `dependencies` recorded

- **DESIGN → BUILD**
  - `outputs.artifacts` includes design docs and interfaces
  - `decisions` include architecture choices

- **BUILD → TEST**
  - `outputs.artifacts` includes code refs and configs
  - `dependencies` updated for test requirements

- **TEST → REVIEW**
  - `outputs.artifacts` includes test refs and results
  - `risks` updated for failing/flake areas

- **REVIEW → DOCUMENT**
  - `outputs.artifacts` includes review notes and required fixes
  - `decisions` updated for accepted changes

- **DOCUMENT → DEPLOY_MAINTAIN**
  - `outputs.artifacts` includes updated docs/runbooks
  - `dependencies` satisfied for release readiness

## Storage & Location
- **Location:** `docs/agent-coordination.md`
- **State Persistence:** Commit updates to this file (or reference an external tracker) for each coordinated run.

## Validation Rules
- `phase` must match `owner_agent` at any point in time.
- `status` cannot move to `COMPLETED` if any `dependencies.status == OPEN`.
- `aws_constraints.aws_only` must remain `true` for all phases.
