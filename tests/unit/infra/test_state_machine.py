from __future__ import annotations

import json
import pathlib
import unittest


class TestStateMachine(unittest.TestCase):
    def setUp(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[4]
        path = repo_root / "infra" / "state-machines" / "claim_orchestration.asl.json"
        self.definition = json.loads(path.read_text(encoding="utf-8"))

    def test_required_states_exist(self) -> None:
        states = self.definition["States"]
        for state_name in [
            "GenerateClaimSummary",
            "RouteClaim",
            "AgentRouter",
            "FraudAgent",
            "FraudCheck",
            "AdjudicationAgent",
            "EvaluateResult",
            "HumanReview",
            "HumanDecisionChoice",
            "FinalizeClaim",
        ]:
            self.assertIn(state_name, states)

    def test_retry_policy_on_generate_summary(self) -> None:
        generate_state = self.definition["States"]["GenerateClaimSummary"]
        retry = generate_state.get("Retry", [])
        self.assertTrue(any("Lambda.TooManyRequestsException" in item.get("ErrorEquals", []) for item in retry))

    def test_fraud_score_threshold(self) -> None:
        fraud_check = self.definition["States"]["FraudCheck"]["Choices"]
        threshold = [choice for choice in fraud_check if choice.get("Variable") == "$.fraud_result.agent_result.structured_findings.fraud_score"]
        self.assertTrue(threshold)
        self.assertEqual(threshold[0].get("NumericGreaterThan"), 0.70)

    def test_guardrail_block_routes_to_hitl(self) -> None:
        evaluate = self.definition["States"]["EvaluateResult"]["Choices"]
        blocked = [choice for choice in evaluate if choice.get("StringEquals") == "BLOCKED"]
        self.assertTrue(blocked)
        self.assertEqual(blocked[0].get("Next"), "HumanReview")


if __name__ == "__main__":
    unittest.main()
