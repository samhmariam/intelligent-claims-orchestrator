from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from icpa.orchestration import agent_wrapper


class TestAgentWrapper(unittest.TestCase):
    def test_parse_agent_result_from_text(self) -> None:
        text = "prefix {\"decision\": \"APPROVE\"} suffix"
        result = agent_wrapper._parse_agent_result(text)
        self.assertEqual(result["decision"], "APPROVE")

    def test_parse_agent_result_raises_on_missing_json(self) -> None:
        with self.assertRaises(ValueError):
            agent_wrapper._parse_agent_result("no json")

    def test_prompt_version_resolves_latest(self) -> None:
        ssm = MagicMock()
        ssm.get_parameter.side_effect = [
            {"Parameter": {"Value": "v1.2.3"}},
            {"Parameter": {"Value": "prompt body"}},
        ]
        with patch("icpa.orchestration.agent_wrapper._ssm", ssm):
            prompt = agent_wrapper._get_prompt("fraud_agent", "latest")
        self.assertEqual(prompt, "prompt body")


if __name__ == "__main__":
    unittest.main()
