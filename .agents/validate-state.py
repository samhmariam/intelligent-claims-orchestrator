#!/usr/bin/env python3
"""
Agent Coordination State Validator

Validates the agent coordination state contract and enforces handoff rules
as defined in docs/agent-coordination.md.

Usage:
    python .agents/validate-state.py --phase DESIGN --check-dependencies
    python .agents/validate-state.py --validate-file docs/coordination-state.json
    python .agents/validate-state.py --init  # Create new state file
"""

import argparse
import json
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4


class Phase(str, Enum):
    PLAN = "PLAN"
    DESIGN = "DESIGN"
    BUILD = "BUILD"
    TEST = "TEST"
    REVIEW = "REVIEW"
    DOCUMENT = "DOCUMENT"
    DEPLOY_MAINTAIN = "DEPLOY_MAINTAIN"


class Status(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"


class ArtifactType(str, Enum):
    PLAN = "PLAN"
    DESIGN = "DESIGN"
    CODE = "CODE"
    TEST = "TEST"
    REVIEW = "REVIEW"
    DOC = "DOC"
    RUNBOOK = "RUNBOOK"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DependencyStatus(str, Enum):
    OPEN = "OPEN"
    SATISFIED = "SATISFIED"


class QuestionStatus(str, Enum):
    OPEN = "OPEN"
    ANSWERED = "ANSWERED"


class ValidationError(Exception):
    """Custom exception for validation failures."""
    pass


class CoordinationStateValidator:
    """Validates agent coordination state against canonical schema."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state: Optional[Dict[str, Any]] = None
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def load_state(self) -> Dict[str, Any]:
        """Load state from JSON file."""
        try:
            with open(self.state_file, 'r') as f:
                self.state = json.load(f)
            return self.state
        except FileNotFoundError:
            raise ValidationError(f"State file not found: {self.state_file}")
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON in state file: {e}")

    def validate_required_fields(self) -> bool:
        """Validate all required fields are present."""
        required_fields = [
            "run_id", "phase", "owner_agent", "status",
            "inputs", "outputs", "dependencies", "risks",
            "open_questions", "aws_constraints"
        ]
        
        for field in required_fields:
            if field not in self.state:
                self.errors.append(f"Missing required field: {field}")
        
        return len(self.errors) == 0

    def validate_uuid(self, value: str, field_name: str) -> bool:
        """Validate UUID format."""
        try:
            UUID(value, version=4)
            return True
        except (ValueError, AttributeError):
            self.errors.append(f"Invalid UUID for {field_name}: {value}")
            return False

    def validate_phase_owner_match(self) -> bool:
        """Validate that phase matches owner_agent."""
        if self.state.get("phase") != self.state.get("owner_agent"):
            self.errors.append(
                f"Phase '{self.state.get('phase')}' must match "
                f"owner_agent '{self.state.get('owner_agent')}'"
            )
            return False
        return True

    def validate_aws_constraints(self) -> bool:
        """Validate AWS-only constraints."""
        constraints = self.state.get("aws_constraints", {})
        
        if not constraints.get("aws_only", False):
            self.errors.append("aws_constraints.aws_only must be true")
        
        if not constraints.get("no_other_clouds", False):
            self.errors.append("aws_constraints.no_other_clouds must be true")
        
        allowed_regions = ["us-east-1", "us-west-2", "eu-west-1"]
        regions = constraints.get("regions", [])
        for region in regions:
            if region not in allowed_regions:
                self.warnings.append(
                    f"Region '{region}' not in approved list: {allowed_regions}"
                )
        
        return len([e for e in self.errors if "aws_constraints" in e]) == 0

    def validate_dependencies(self) -> Tuple[bool, List[str]]:
        """Validate dependencies and return open dependencies."""
        dependencies = self.state.get("dependencies", [])
        open_deps = []
        
        for dep in dependencies:
            required = ["from_phase", "to_phase", "status", "note"]
            for field in required:
                if field not in dep:
                    self.errors.append(f"Dependency missing field: {field}")
            
            if dep.get("status") == DependencyStatus.OPEN.value:
                open_deps.append(
                    f"{dep.get('from_phase')} -> {dep.get('to_phase')}: "
                    f"{dep.get('note')}"
                )
        
        return len(open_deps) == 0, open_deps

    def validate_completion_criteria(self) -> bool:
        """Validate that status cannot be COMPLETED if dependencies are OPEN."""
        if self.state.get("status") == Status.COMPLETED.value:
            all_deps_satisfied, open_deps = self.validate_dependencies()
            if not all_deps_satisfied:
                self.errors.append(
                    f"Cannot mark status as COMPLETED with open dependencies:\n"
                    + "\n".join(f"  - {dep}" for dep in open_deps)
                )
                return False
        return True

    def validate_handoff_requirements(self) -> Tuple[bool, List[str]]:
        """Validate handoff requirements for current phase."""
        phase = self.state.get("phase")
        outputs = self.state.get("outputs", {})
        artifacts = outputs.get("artifacts", [])
        decisions = outputs.get("decisions", [])
        missing = []

        handoff_rules = {
            Phase.PLAN: {
                "inputs": ["requirements_refs"],
                "outputs": ["open_questions", "dependencies"],
                "artifacts": [ArtifactType.PLAN]
            },
            Phase.DESIGN: {
                "inputs": ["requirements_refs", "design_refs"],
                "outputs": ["artifacts", "decisions"],
                "artifacts": [ArtifactType.DESIGN]
            },
            Phase.BUILD: {
                "inputs": ["design_refs"],
                "outputs": ["artifacts"],
                "artifacts": [ArtifactType.CODE]
            },
            Phase.TEST: {
                "inputs": ["code_refs"],
                "outputs": ["artifacts", "risks"],
                "artifacts": [ArtifactType.TEST]
            },
            Phase.REVIEW: {
                "inputs": ["code_refs", "test_refs"],
                "outputs": ["artifacts", "decisions"],
                "artifacts": [ArtifactType.REVIEW]
            },
            Phase.DOCUMENT: {
                "inputs": ["code_refs", "doc_refs"],
                "outputs": ["artifacts"],
                "artifacts": [ArtifactType.DOC]
            },
            Phase.DEPLOY_MAINTAIN: {
                "inputs": ["runbook_refs"],
                "outputs": ["artifacts"],
                "artifacts": [ArtifactType.RUNBOOK]
            }
        }

        if phase not in [p.value for p in Phase]:
            self.errors.append(f"Invalid phase: {phase}")
            return False, []

        rules = handoff_rules.get(Phase(phase), {})
        
        # Check required input refs
        inputs = self.state.get("inputs", {})
        for input_ref in rules.get("inputs", []):
            if not inputs.get(input_ref):
                missing.append(f"inputs.{input_ref}")
        
        # Check required output fields
        for output_field in rules.get("outputs", []):
            if output_field == "artifacts" and not artifacts:
                missing.append("outputs.artifacts")
            elif output_field == "decisions" and not decisions:
                missing.append("outputs.decisions")
            elif output_field == "open_questions":
                if not self.state.get("open_questions"):
                    missing.append("open_questions")
            elif output_field == "dependencies":
                if not self.state.get("dependencies"):
                    missing.append("dependencies")
            elif output_field == "risks":
                if not self.state.get("risks"):
                    missing.append("risks")
        
        # Check required artifact types
        artifact_types = [a.get("type") for a in artifacts]
        for required_type in rules.get("artifacts", []):
            if required_type.value not in artifact_types:
                missing.append(f"artifact type: {required_type.value}")
        
        return len(missing) == 0, missing

    def validate(self) -> bool:
        """Run all validations."""
        self.errors = []
        self.warnings = []
        
        try:
            self.load_state()
        except ValidationError as e:
            self.errors.append(str(e))
            return False
        
        # Required field validation
        if not self.validate_required_fields():
            return False
        
        # UUID validation
        self.validate_uuid(self.state.get("run_id"), "run_id")
        if self.state.get("claim_id"):
            self.validate_uuid(self.state.get("claim_id"), "claim_id")
        
        # Business rule validations
        self.validate_phase_owner_match()
        self.validate_aws_constraints()
        self.validate_completion_criteria()
        
        # Handoff validation
        handoff_valid, missing = self.validate_handoff_requirements()
        if not handoff_valid and self.state.get("status") == Status.COMPLETED.value:
            self.errors.append(
                f"Cannot complete phase with missing handoff requirements:\n"
                + "\n".join(f"  - {item}" for item in missing)
            )
        elif not handoff_valid:
            self.warnings.append(
                f"Incomplete handoff requirements (allowed for IN_PROGRESS):\n"
                + "\n".join(f"  - {item}" for item in missing)
            )
        
        return len(self.errors) == 0

    def report(self) -> str:
        """Generate validation report."""
        report = []
        report.append("=" * 70)
        report.append("AGENT COORDINATION STATE VALIDATION REPORT")
        report.append("=" * 70)
        report.append(f"State File: {self.state_file}")
        report.append(f"Validation Time: {datetime.utcnow().isoformat()}Z")
        report.append("")
        
        if self.state:
            report.append(f"Run ID: {self.state.get('run_id')}")
            report.append(f"Phase: {self.state.get('phase')}")
            report.append(f"Owner Agent: {self.state.get('owner_agent')}")
            report.append(f"Status: {self.state.get('status')}")
            report.append("")
        
        if self.errors:
            report.append("❌ ERRORS:")
            for error in self.errors:
                report.append(f"  - {error}")
            report.append("")
        
        if self.warnings:
            report.append("⚠️  WARNINGS:")
            for warning in self.warnings:
                report.append(f"  - {warning}")
            report.append("")
        
        if not self.errors:
            report.append("✅ VALIDATION PASSED")
        else:
            report.append(f"❌ VALIDATION FAILED ({len(self.errors)} errors)")
        
        report.append("=" * 70)
        return "\n".join(report)


def create_initial_state(output_file: Path, phase: Phase) -> Dict[str, Any]:
    """Create a new coordination state file."""
    state = {
        "run_id": str(uuid4()),
        "claim_id": None,
        "phase": phase.value,
        "owner_agent": phase.value,
        "status": Status.NOT_STARTED.value,
        "inputs": {
            "requirements_refs": [],
            "design_refs": [],
            "code_refs": [],
            "test_refs": [],
            "doc_refs": [],
            "runbook_refs": []
        },
        "outputs": {
            "artifacts": [],
            "decisions": []
        },
        "dependencies": [],
        "risks": [],
        "open_questions": [],
        "aws_constraints": {
            "aws_only": True,
            "no_other_clouds": True,
            "regions": ["us-east-1"],
            "network": "Private subnets, no NAT, VPC endpoints"
        }
    }
    
    with open(output_file, 'w') as f:
        json.dump(state, f, indent=2)
    
    return state


def main():
    parser = argparse.ArgumentParser(
        description="Validate agent coordination state contract"
    )
    parser.add_argument(
        "--validate-file",
        type=Path,
        default=Path("docs/coordination-state.json"),
        help="Path to coordination state JSON file"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize a new coordination state file"
    )
    parser.add_argument(
        "--phase",
        type=str,
        choices=[p.value for p in Phase],
        default=Phase.PLAN.value,
        help="Initial phase for new state file"
    )
    parser.add_argument(
        "--check-dependencies",
        action="store_true",
        help="Check for open dependencies"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed validation output"
    )
    
    args = parser.parse_args()
    
    # Initialize new state file if requested
    if args.init:
        state = create_initial_state(args.validate_file, Phase(args.phase))
        print(f"✅ Created new state file: {args.validate_file}")
        print(f"   Run ID: {state['run_id']}")
        print(f"   Phase: {state['phase']}")
        return 0
    
    # Validate existing state file
    validator = CoordinationStateValidator(args.validate_file)
    is_valid = validator.validate()
    
    # Generate and print report
    report = validator.report()
    print(report)
    
    # Check dependencies if requested
    if args.check_dependencies:
        all_deps_satisfied, open_deps = validator.validate_dependencies()
        if not all_deps_satisfied:
            print("\n⚠️  OPEN DEPENDENCIES:")
            for dep in open_deps:
                print(f"  - {dep}")
    
    # Exit with appropriate code
    return 0 if is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
