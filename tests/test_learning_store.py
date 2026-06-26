import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.learning_store import load_learning_store, save_learning_store


class LearningStoreTests(unittest.TestCase):
    def test_learning_store_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "learning_store.json"
            payload = {
                "class_training_examples": [
                    {
                        "label": "Invoice",
                        "text": "Invoice Number INV-1 Total 100.00",
                        "source": "unit_test",
                    }
                ],
                "field_training_examples": [
                    {
                        "document_class": "Invoice",
                        "field_name": "invoice_number",
                        "corrected_value": "INV-1",
                        "learned_label": "Invoice Number",
                        "source": "unit_test",
                    }
                ],
                "learned_field_aliases": {"Invoice": {"invoice_number": ["Invoice Number"]}},
                "review_training_events": [{"action": "Approve"}],
                "model_version": 7,
            }

            success, _ = save_learning_store(payload, path=path)
            loaded, _ = load_learning_store(path=path)

            self.assertTrue(success)
            self.assertEqual(loaded["model_version"], 7)
            self.assertEqual(loaded["class_training_examples"][0]["label"], "Invoice")
            self.assertEqual(
                loaded["learned_field_aliases"]["Invoice"]["invoice_number"],
                ["Invoice Number"],
            )


if __name__ == "__main__":
    unittest.main()
