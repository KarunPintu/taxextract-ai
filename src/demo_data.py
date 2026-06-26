from typing import Dict, List


def _invoice_text(
    invoice_number: str = "INV-1001",
    subtotal: str = "$1,000.00",
    tax_amount: str = "$82.50",
    total_amount: str = "$1,082.50",
    vendor: str = "Sample Vendor LLC",
    client: str = "Demo Property Group",
) -> str:
    return f"""
Invoice
Invoice Number: {invoice_number}
Invoice Date: 2026-03-01
Vendor: {vendor}
Client: {client}
Client Address: 100 Demo Center Drive
Subtotal: {subtotal}
Tax Amount: {tax_amount}
Total Amount: {total_amount}
Currency: USD
Due Date: 2026-03-31
Line Items: Tax document processing and account support
"""


def _assessment_text(
    assessment_year: str = "2026",
    parcel_id: str = "PAR-4451-220",
    assessed_value: str = "$240,000.00",
    taxable_value: str = "$220,000.00",
    market_value: str = "$260,000.00",
    exemption_value: str = "$20,000.00",
    owner_name: str = "Sample Owner Trust",
) -> str:
    return f"""
Assessment Notice
Assessment Year: {assessment_year}
Owner Name: {owner_name}
Owner Address: 42 Demo Lane
City: Sampleton
State: ST
ZIP: 12345
Parcel ID: {parcel_id}
County: Demo County
Acreage: 2.5
Assessed Value: {assessed_value}
Taxable Value: {taxable_value}
Market Value: {market_value}
Exemption Value: {exemption_value}
Notice Date: 2026-05-01
Appeal Deadline: 2026-06-15
"""


def _tax_bill_text(
    bill_number: str = "TB-9001",
    tax_year: str = "2026",
    parcel_id: str = "PAR-7755-991",
    owner_name: str = "Demo Owner LLC",
    tax_amount: str = "$4,000.00",
    total_due: str = "$4,100.00",
    assessed_value: str = "$250,000.00",
    taxable_value: str = "$225,000.00",
    market_value: str = "$275,000.00",
    exemption_value: str = "$25,000.00",
    installment_1: str = "$2,050.00",
    installment_2: str = "$2,050.00",
) -> str:
    return f"""
Tax Bill
Tax Bill Number: {bill_number}
Tax Year: {tax_year}
Owner Name: {owner_name}
Owner Address: 77 Demo Plaza
City: Sampleton
State: ST
ZIP: 12345
Parcel ID: {parcel_id}
County or Jurisdiction: Demo County
Tax Amount: {tax_amount}
Penalty Amount: $75.00
Interest Amount: $25.00
Total Due: {total_due}
Due Date: 2026-12-31
Assessed Value: {assessed_value}
Taxable Value: {taxable_value}
Market Value: {market_value}
Exemption Value: {exemption_value}
Installment 1: {installment_1}
Installment 1 Due Date: 2026-06-30
Installment 2: {installment_2}
Installment 2 Due Date: 2026-12-31
"""


SAMPLE_SCENARIOS: Dict[str, Dict[str, object]] = {
    "invoice_clean_01.pdf": {
        "document_class": "Invoice",
        "scenario": "Clean",
        "expected_outcome": "Pass",
        "scanned": False,
        "text": _invoice_text(),
    },
    "invoice_scanned_01.pdf": {
        "document_class": "Invoice",
        "scenario": "Scanned",
        "expected_outcome": "Needs Review/OCR",
        "scanned": True,
        "ocr_confidence": 62.0,
        "text": _invoice_text(invoice_number="INV-SCAN-01", total_amount="$1,082.50"),
    },
    "invoice_number_missing_01.pdf": {
        "document_class": "Invoice",
        "scenario": "Missing field",
        "expected_outcome": "Needs Review",
        "scanned": False,
        "text": _invoice_text(invoice_number=""),
    },
    "invoice_total_amount_mismatch01.pdf": {
        "document_class": "Invoice",
        "scenario": "Amount mismatch",
        "expected_outcome": "Needs Review",
        "scanned": False,
        "text": _invoice_text(total_amount="$1,125.00"),
    },
    "assessment_01.pdf": {
        "document_class": "Assessment",
        "scenario": "Clean",
        "expected_outcome": "Pass",
        "scanned": False,
        "text": _assessment_text(),
    },
    "assessment_missing_year_01.pdf": {
        "document_class": "Assessment",
        "scenario": "Missing field",
        "expected_outcome": "Needs Review",
        "scanned": False,
        "text": _assessment_text(assessment_year=""),
    },
    "assessment_total_mismatch_01.pdf": {
        "document_class": "Assessment",
        "scenario": "Amount mismatch",
        "expected_outcome": "Needs Review",
        "scanned": False,
        "text": _assessment_text(assessed_value="$240,000.00", taxable_value="$230,000.00", exemption_value="$20,000.00"),
    },
    "parcel_number_missing_01.pdf": {
        "document_class": "Assessment",
        "scenario": "Missing field",
        "expected_outcome": "Needs Review",
        "scanned": False,
        "text": _assessment_text(parcel_id=""),
    },
    "tax_bill_total_mismatch_01.pdf": {
        "document_class": "Tax Bill",
        "scenario": "Amount mismatch",
        "expected_outcome": "Needs Review",
        "scanned": False,
        "text": _tax_bill_text(assessed_value="$250,000.00", taxable_value="$235,000.00", exemption_value="$25,000.00"),
    },
    "tax_bill_01.pdf": {
        "document_class": "Tax Bill",
        "scenario": "Clean",
        "expected_outcome": "Pass",
        "scanned": False,
        "text": _tax_bill_text(),
    },
    "tax_bill_installments_mismatch_01.pdf": {
        "document_class": "Tax Bill",
        "scenario": "Installments amount mismatch",
        "expected_outcome": "Needs Review",
        "scanned": False,
        "text": _tax_bill_text(installment_1="$1,800.00", installment_2="$2,050.00"),
    },
    "tax_bill_ownername_missing_01.pdf": {
        "document_class": "Tax Bill",
        "scenario": "Missing field",
        "expected_outcome": "Needs Review",
        "scanned": False,
        "text": _tax_bill_text(owner_name=""),
    },
    "tax_bill_scanned_01.pdf": {
        "document_class": "Tax Bill",
        "scenario": "Scanned",
        "expected_outcome": "Needs Review/OCR",
        "scanned": True,
        "ocr_confidence": 66.0,
        "text": _tax_bill_text(bill_number="TB-SCAN-01"),
    },
}


DEMO_DASHBOARD_ROWS: List[Dict[str, object]] = [
    {
        "document_id": "DEMO-1001",
        "file_name": "invoice_clean_01.pdf",
        "document_class": "Invoice",
        "classification_confidence": 94,
        "processing_status": "Validation Completed",
        "validation_status": "Passed",
        "review_status": "Not Required",
        "export_status": "Ready",
        "uploaded_at": "2026-06-23T09:10:00",
    },
    {
        "document_id": "DEMO-1002",
        "file_name": "assessment_total_mismatch_01.pdf",
        "document_class": "Assessment",
        "classification_confidence": 92,
        "processing_status": "Review Required",
        "validation_status": "Failed",
        "review_status": "Needs Review",
        "export_status": "Blocked",
        "uploaded_at": "2026-06-23T09:18:00",
    },
    {
        "document_id": "DEMO-1003",
        "file_name": "tax_bill_scanned_01.pdf",
        "document_class": "Tax Bill",
        "classification_confidence": 89,
        "processing_status": "Review Required",
        "validation_status": "Warning",
        "review_status": "Needs Review",
        "export_status": "Blocked",
        "uploaded_at": "2026-06-23T09:27:00",
    },
]


def get_sample_scenario(file_name: str) -> Dict[str, object] | None:
    return SAMPLE_SCENARIOS.get((file_name or "").lower())


def sample_file_names() -> List[str]:
    return list(SAMPLE_SCENARIOS.keys())
