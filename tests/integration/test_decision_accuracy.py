from __future__ import annotations

import json
import pathlib
import unittest


class TestDecisionAccuracy(unittest.TestCase):
    def test_golden_set_accuracy(self) -> None:
        path = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "golden_set_results.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases = payload["cases"]
        correct = sum(1 for case in cases if case["expected_decision"] == case["actual_decision"])
        accuracy = correct / max(len(cases), 1)
        self.assertGreaterEqual(accuracy, 0.90)


if __name__ == "__main__":
    unittest.main()
