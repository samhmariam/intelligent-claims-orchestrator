from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from icpa.ingestion import handlers


class TestIngestionHandlers(unittest.TestCase):
    def test_chunk_text_limits(self) -> None:
        text = "a" * 50_000
        chunks = list(handlers._chunk_text(text))
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 18_000 for chunk in chunks))
        self.assertGreaterEqual(len("".join(chunks)), 50_000)

    def test_phi_detected_true_when_entity_above_threshold(self) -> None:
        client = MagicMock()
        client.detect_phi.return_value = {
            "Entities": [
                {"Type": "NAME", "Score": 0.95},
            ]
        }
        detected = handlers._phi_detected(client, "sample text", 0.90)
        self.assertTrue(detected)

    def test_analyze_image_fallback(self) -> None:
        textract = MagicMock()
        textract.analyze_document.return_value = {"Blocks": []}
        textract.detect_document_text.return_value = {
            "Blocks": [
                {"BlockType": "LINE", "Text": "hello", "Page": 1}
            ]
        }
        text, page_count = handlers._analyze_image(textract, "bucket", "key.jpg")
        self.assertEqual(text, "hello")
        self.assertEqual(page_count, 1)

    def test_textract_result_fallback_detect_document_text(self) -> None:
        env = handlers.EnvConfig(
            raw_bucket="raw-bucket",
            clean_bucket="clean-bucket",
            quarantine_bucket="quarantine-bucket",
            transcribe_output_bucket="clean-bucket",
            textract_role_arn=None,
            textract_sns_topic_arn=None,
            phi_threshold=0.90,
            region="us-east-1",
        )
        s3 = MagicMock()
        events = MagicMock()
        comprehend = MagicMock()
        comprehend.detect_phi.return_value = {"Entities": []}
        textract = MagicMock()
        textract.get_document_analysis.side_effect = [
            {"Blocks": [], "NextToken": None}
        ]
        textract.detect_document_text.return_value = {
            "Blocks": [
                {"BlockType": "LINE", "Text": "fallback", "Page": 1}
            ]
        }
        with patch("icpa.ingestion.handlers._env", return_value=env), patch(
            "icpa.ingestion.handlers._clients",
            return_value={
                "s3": s3,
                "textract": textract,
                "transcribe": MagicMock(),
                "comprehend_medical": comprehend,
                "events": events,
            },
        ):
            result = handlers.textract_result_handler(
                {
                    "detail": {
                        "JobId": "job-1",
                        "JobTag": "claim_id=cid;doc_id=did;clean_uri=s3://clean-bucket/cid/doc_id=did/file.pdf",
                    }
                },
                None,
            )
        self.assertEqual(result["status"], "EXTRACTED")
        self.assertEqual(result["claim_id"], "cid")


if __name__ == "__main__":
    unittest.main()
