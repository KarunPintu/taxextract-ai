import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.classifier import classify_document


class HybridClassifierTests(unittest.TestCase):
    def test_invoice_classifier_uses_hybrid_result_when_available(self):
        text = """
Invoice
Invoice Number: INV-100
Vendor: Sample Vendor LLC
Bill To: Demo Client
Subtotal: 100.00
Tax Amount: 8.00
Total Amount: 108.00
Due Date: 2026-05-01
"""
        result = classify_document(text, file_name="invoice.pdf")

        self.assertEqual(result["document_class"], "Invoice")
        self.assertGreaterEqual(result["confidence"], 70)
        self.assertIn(result["classifier_type"], ["Hybrid Rules + Local ML", "Rules only"])

    def test_user_training_feedback_can_shift_classification(self):
        ambiguous_text = """
Statement
Parcel ID: PAR-99
Tax Year: 2026
Total Due: 4,100.00
Installment 1 Due Date: 2026-06-30
Installment 2 Due Date: 2026-12-31
"""
        result = classify_document(
            ambiguous_text,
            file_name="statement.pdf",
            user_training_examples=[
                {
                    "label": "Tax Bill",
                    "text": ambiguous_text,
                    "source": "unit_test",
                }
            ],
        )

        self.assertEqual(result["document_class"], "Tax Bill")
        self.assertGreaterEqual(result["confidence"], 55)

    def test_personal_property_assessment_classifies_with_market_information(self):
        text = """
RECORD SUMMARY
Tax Year:
2026
Parcel:
4950 000 50 793
Owner:
BFI WASTE SERVICES LLC
Business Type:
4950 - SANITARY SERVICES
Economic Life:
8
Market Information
Market Value
Assessment Value
Exempt Value
Total Taxable
$390,576
$78,120
$0
$78,120
"""
        result = classify_document(text, file_name="PTX - 4950 000 50 793 - Morgan Co..pdf")

        self.assertEqual(result["document_class"], "Assessment")
        self.assertGreaterEqual(result["confidence"], 80)
        self.assertIn("market information", result["matching_keywords"])

    def test_illinois_tax_bill_classifies_with_equalized_value_and_installments(self):
        text = """
Bureau County
2025 Real Estate Taxes payable in 2026
PIN 15-16-351-001
State Equalized Value
Net Taxable Value
Real Estate Tax
Total Tax Due
1st Installment Due 07/22/2026 for $52.92
2nd Installment Due 09/22/2026 for $52.92
County Collector Treasurer
"""
        result = classify_document(text, file_name="15-16-351-001.pdf")

        self.assertEqual(result["document_class"], "Tax Bill")
        self.assertGreaterEqual(result["confidence"], 80)
        self.assertIn("state equalized value", result["matching_keywords"])


if __name__ == "__main__":
    unittest.main()
