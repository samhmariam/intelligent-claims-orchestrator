from __future__ import annotations

from decimal import Decimal
import unittest

from icpa import db_client


class TestDbClient(unittest.TestCase):
    def test_to_dynamo_compatible_converts_floats(self) -> None:
        payload = {
            "score": 0.42,
            "nested": {"value": 1.5},
            "items": [0.1, {"x": 2.25}],
        }
        result = db_client._to_dynamo_compatible(payload)

        self.assertIsInstance(result["score"], Decimal)
        self.assertEqual(result["score"], Decimal("0.42"))
        self.assertEqual(result["nested"]["value"], Decimal("1.5"))
        self.assertEqual(result["items"][0], Decimal("0.1"))
        self.assertEqual(result["items"][1]["x"], Decimal("2.25"))


if __name__ == "__main__":
    unittest.main()
