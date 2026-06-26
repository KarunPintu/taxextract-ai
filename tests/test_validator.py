import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.validator import summarize_validation_status, validate_document


class ValidatorTests(unittest.TestCase):
    def test_invoice_clean_passes(self):
        fields = {
            "invoice_number": "INV-1",
            "invoice_date": "2026-03-01",
            "vendor_name": "Sample Vendor LLC",
            "client_name": "Demo Client",
            "subtotal": 100.00,
            "tax_amount": 8.25,
            "total_amount": 108.25,
            "due_date": "2026-03-31",
        }
        results = validate_document("Invoice", fields)
        self.assertEqual(summarize_validation_status(results), "Passed")

    def test_invoice_total_mismatch_fails(self):
        fields = {
            "invoice_number": "INV-2",
            "invoice_date": "2026-03-01",
            "vendor_name": "Sample Vendor LLC",
            "client_name": "Demo Client",
            "subtotal": 100.00,
            "tax_amount": 8.25,
            "total_amount": 120.00,
            "due_date": "2026-03-31",
        }
        results = validate_document("Invoice", fields)
        failed_rules = [result["rule_id"] for result in results if result["status"] == "failed"]
        self.assertIn("invoice_amount_reconciliation", failed_rules)

    def test_assessment_missing_year_fails(self):
        fields = {
            "assessment_year": "",
            "owner_name": "Sample Owner",
            "parcel_id": "PAR-1",
            "assessed_value": 240000.00,
            "taxable_value": 220000.00,
            "market_value": 260000.00,
            "exemption_value": 20000.00,
        }
        results = validate_document("Assessment", fields)
        self.assertEqual(summarize_validation_status(results), "Failed")

    def test_tax_bill_installment_mismatch_fails(self):
        fields = {
            "tax_bill_number": "TB-1",
            "tax_year": "2026",
            "owner_name": "Demo Owner",
            "parcel_id": "PAR-2",
            "tax_amount": 4000.00,
            "total_due": 4100.00,
            "assessed_value": 250000.00,
            "taxable_value": 225000.00,
            "market_value": 275000.00,
            "exemption_value": 25000.00,
            "installment_1": 1800.00,
            "installment_1_due_date": "2026-06-30",
            "installment_2": 2050.00,
            "installment_2_due_date": "2026-12-31",
        }
        results = validate_document("Tax Bill", fields)
        failed_rules = [result["rule_id"] for result in results if result["status"] == "failed"]
        self.assertIn("tax_bill_installment_reconciliation", failed_rules)

    def test_duplicate_invoice_number_warns(self):
        fields = {
            "invoice_number": "INV-DUP",
            "invoice_date": "2026-03-01",
            "vendor_name": "Sample Vendor LLC",
            "client_name": "Demo Client",
            "subtotal": 100.00,
            "tax_amount": 8.25,
            "total_amount": 108.25,
            "due_date": "2026-03-31",
        }
        existing_documents = [
            {
                "document_id": "DOC-1",
                "document_class": "Invoice",
                "normalized_fields": {"invoice_number": "INV-DUP"},
            }
        ]
        results = validate_document(
            "Invoice",
            fields,
            existing_documents=existing_documents,
            current_document_id="DOC-2",
        )
        warning_rules = [result["rule_id"] for result in results if result["status"] == "warning"]
        self.assertIn("invoice_duplicate_invoice_number", warning_rules)


if __name__ == "__main__":
    unittest.main()
