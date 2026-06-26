import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.extractor_assessment import extract_assessment_fields
from src.extractor_invoice import extract_invoice_fields
from src.extractor_tax_bill import extract_tax_bill_fields
from src.normalizer import normalize_fields


class ExtractionEngineTests(unittest.TestCase):
    def test_multiline_invoice_values_are_mapped_to_correct_fields(self):
        text = """
Invoice Number :
Q200593825
Invoice date :
31 Oct 2023
Total :
3,461.54
"""
        result = extract_invoice_fields(text, include_metadata=True)
        normalized = normalize_fields("Invoice", result["fields"])

        self.assertEqual(result["fields"]["invoice_number"], "Q200593825")
        self.assertEqual(result["fields"]["invoice_date"], "31 Oct 2023")
        self.assertEqual(normalized["total_amount"], 3461.54)
        self.assertGreaterEqual(result["metadata"]["invoice_number"]["confidence"], 0.8)
        self.assertIn("Invoice Number", result["metadata"]["invoice_number"]["source_line"])

    def test_invoice_payment_reference_is_not_used_as_invoice_number(self):
        text = """
Invoice
Invoice Number :
Q200593825
Invoice date :
31 Oct 2023
Payment Reference Number : PR20324172
Please note payment reference number PR20324172 when paying.
Total
3,461.54
"""
        result = extract_invoice_fields(text, include_metadata=True)

        self.assertEqual(result["fields"]["invoice_number"], "Q200593825")
        self.assertNotEqual(result["fields"]["invoice_number"], "PR20324172")

    def test_apple_style_invoice_layout_extracts_header_and_amounts(self):
        text = """
Search Ads
Invoice
Customer Number :
1388165
Reference :
Invoice Number :
Q200593825
Invoice date :
31 Oct 2023
Billing Period :
01 Oct 2023 - 31 Oct 2023
Customer Name and Address
HOME24
HOME24 SE
Page 1 / 1
Apple Distribution International Ltd.
Hollyhill Industrial Estate
Payment Reference Number : PR20324172
Wire Transfer / ACH
Account Number : 01001765
Subtotal
3,461.54
VAT Charged 0%
0.00
Total
3,461.54
15 Dec 2023
Due Date :
"""
        result = extract_invoice_fields(text, include_metadata=True)
        normalized = normalize_fields("Invoice", result["fields"])

        self.assertEqual(result["fields"]["invoice_number"], "Q200593825")
        self.assertEqual(result["fields"]["vendor_name"], "Apple Distribution International Ltd.")
        self.assertEqual(result["fields"]["client_name"], "HOME24")
        self.assertEqual(normalized["subtotal"], 3461.54)
        self.assertEqual(normalized["tax_amount"], 0.0)
        self.assertEqual(normalized["total_amount"], 3461.54)
        self.assertEqual(normalized["due_date"], "2023-12-15")

    def test_missing_invoice_number_stays_blank(self):
        text = """
Invoice
Invoice Number :
Invoice Date : 2026-03-01
Vendor: Sample Vendor LLC
Client: Demo Client
Subtotal: 100.00
Tax Amount: 8.25
Total Amount: 108.25
"""
        result = extract_invoice_fields(text, include_metadata=True)

        self.assertEqual(result["fields"]["invoice_number"], "")
        self.assertEqual(result["metadata"]["invoice_number"]["confidence"], 0.0)

    def test_invoice_summary_table_layout_extracts_values(self):
        text = """
Supplier Invoice
Invoice Number    Invoice Date    Due Date    Subtotal    Tax Amount    Total Amount
INV-77881         2026-04-02      2026-05-02  1,200.00    96.00         1,296.00
Vendor Name : Layout Two Services LLC
Bill To : Demo Buyer Inc
"""
        result = extract_invoice_fields(text, include_metadata=True)
        normalized = normalize_fields("Invoice", result["fields"])

        self.assertEqual(result["fields"]["invoice_number"], "INV-77881")
        self.assertEqual(normalized["invoice_date"], "2026-04-02")
        self.assertEqual(normalized["due_date"], "2026-05-02")
        self.assertEqual(normalized["subtotal"], 1200.0)
        self.assertEqual(normalized["tax_amount"], 96.0)
        self.assertEqual(normalized["total_amount"], 1296.0)
        self.assertEqual(result["metadata"]["total_amount"]["extraction_method"], "table_row")

    def test_wrapped_service_invoice_layout_extracts_values(self):
        text = """
Style China Limited
Room 2208
Comnercial Building
Shenzhen, PR China
To?
hone24 SE
0tto-0strowski-Str.
10249 Berlin
Invoice No:
Invoice date:
2023-3600009
2023/9/30
Period
ification of services
Unit
Amount Currenc
Sep-23
Management and operation consulting
1
330,229.12
CNY
fees of Supply chain / QC services
Tax (670)
19,813,75
less advance payments already made
0.00
Amount to be paid
"""
        result = extract_invoice_fields(text, include_metadata=True)
        normalized = normalize_fields("Invoice", result["fields"])

        self.assertEqual(result["fields"]["invoice_number"], "2023-3600009")
        self.assertEqual(normalized["invoice_date"], "2023-09-30")
        self.assertEqual(result["fields"]["vendor_name"], "Style China Limited")
        self.assertEqual(result["fields"]["client_name"], "hone24 SE")
        self.assertEqual(normalized["subtotal"], 330229.12)
        self.assertEqual(normalized["tax_amount"], 19813.75)
        self.assertEqual(normalized["total_amount"], 350042.87)
        self.assertEqual(result["fields"]["currency"], "CNY")

    def test_assessment_fields_use_class_specific_specs(self):
        text = """
Assessment Notice
Assessment Year :
2026
Owner Name :
Sample Owner Trust
Parcel ID :
PAR-4451-220
Assessed Value :
240,000.00
Taxable Value :
220,000.00
Market Value :
260,000.00
Exemption Value :
20,000.00
"""
        result = extract_assessment_fields(text, include_metadata=True)
        normalized = normalize_fields("Assessment", result["fields"])

        self.assertEqual(result["fields"]["assessment_year"], "2026")
        self.assertEqual(result["fields"]["parcel_id"], "PAR-4451-220")
        self.assertEqual(normalized["assessed_value"], 240000.0)
        self.assertGreater(result["metadata"]["parcel_id"]["confidence"], 0.7)

    def test_assessment_record_summary_layout_extracts_spaced_parcel_and_values(self):
        text = """
Printed on: 6/5/2026
RECORD SUMMARY
Tax Year:
2026
Parcel:
02 05 22 0 001 003.007
Owner:
FLINTROCK LLC
Address:
1821 BAYSHORE BLVD
TAMPA FL 33606
Neighborhood:
HWY20CO&IN
Acreage:
0.000
Valuation Summary
Total Improvement Value:
$333,200
Total Land Value:
$104,500
Total Market Value:
$437,700
Total Appraised Value:
$437,700
Assessed Value:
$73,200
Ownership History
Tax Year
Entity Name
Mailing Address
2026
FLINTROCK LLC
1821 BAYSHORE BLVD TAMPA FL 33606
Building 1 Information
Value
$250,296.00
"""
        result = extract_assessment_fields(text, include_metadata=True)
        normalized = normalize_fields("Assessment", result["fields"])

        self.assertEqual(result["fields"]["assessment_year"], "2026")
        self.assertEqual(result["fields"]["parcel_id"], "02 05 22 0 001 003.007")
        self.assertEqual(result["fields"]["owner_name"], "FLINTROCK LLC")
        self.assertEqual(result["fields"]["owner_address"], "1821 BAYSHORE BLVD TAMPA FL 33606")
        self.assertEqual(normalized["market_value"], 437700.0)
        self.assertEqual(normalized["assessed_value"], 73200.0)
        self.assertEqual(normalized["taxable_value"], 73200.0)
        self.assertNotEqual(result["fields"]["owner_address"], "2026")
        self.assertNotEqual(normalized["assessed_value"], 250296.0)
        self.assertEqual(
            result["metadata"]["parcel_id"]["extraction_method"],
            "assessment_record_summary",
        )

    def test_personal_property_assessment_market_information_table_extracts_values(self):
        text = """
Printed on: 6/5/2026
RECORD SUMMARY
Tax Year:
2026
Parcel:
4950 000 50 793
Owner:
BFI WASTE SERVICES LLC
Mailing Address:
C/O REPUBLIC SERVICES PROPERTY
PO BOX 29246
PHOENIX AZ 85038
DBA Address
DECATUR LOCATIONS
AL 35602
Business Type:
4950 - SANITARY SERVICES
Market Information
Market Value
Assessment Value
Exempt Value
Abatement
Penalty
Total Taxable
$390,576
$78,120
$0
$0
$0
$78,120
Payment Information
Tax Year
Paid By
Total Tax Plus Fees
2025
AWIN MANAGEMENT INC/MAIL
$4,210.73
"""
        result = extract_assessment_fields(text, include_metadata=True)
        normalized = normalize_fields("Assessment", result["fields"])

        self.assertEqual(result["fields"]["assessment_year"], "2026")
        self.assertEqual(result["fields"]["parcel_id"], "4950 000 50 793")
        self.assertEqual(result["fields"]["owner_name"], "BFI WASTE SERVICES LLC")
        self.assertEqual(
            result["fields"]["owner_address"],
            "C/O REPUBLIC SERVICES PROPERTY PO BOX 29246 PHOENIX AZ 85038",
        )
        self.assertEqual(normalized["market_value"], 390576.0)
        self.assertEqual(normalized["assessed_value"], 78120.0)
        self.assertEqual(normalized["taxable_value"], 78120.0)
        self.assertEqual(normalized["exemption_value"], 0.0)
        self.assertEqual(
            result["metadata"]["assessed_value"]["extraction_method"],
            "assessment_market_information_table",
        )

    def test_tax_bill_installments_are_not_confused_with_due_dates(self):
        text = """
Tax Bill
Tax Bill Number :
TB-9001
Tax Year :
2026
Owner Name :
Demo Owner LLC
Parcel ID :
PAR-7755-991
Tax Amount :
4,000.00
Total Due :
4,100.00
Assessed Value :
250,000.00
Taxable Value :
225,000.00
Market Value :
275,000.00
Exemption Value :
25,000.00
Installment 1 :
2,050.00
Installment 1 Due Date :
2026-06-30
Installment 2 :
2,050.00
Installment 2 Due Date :
2026-12-31
"""
        result = extract_tax_bill_fields(text, include_metadata=True)
        normalized = normalize_fields("Tax Bill", result["fields"])

        self.assertEqual(result["fields"]["tax_bill_number"], "TB-9001")
        self.assertEqual(normalized["installment_1"], 2050.0)
        self.assertEqual(normalized["installment_2"], 2050.0)
        self.assertEqual(normalized["installment_1_due_date"], "2026-06-30")
        self.assertEqual(normalized["installment_2_due_date"], "2026-12-31")

    def test_illinois_tax_bill_extracts_equalized_taxable_and_installments(self):
        text = """
Bureau County
Joseph Birkey, County Collector/Treasurer
2025 Real Estate Taxes (payable in 2026)
Land
Building
1,400
0
1,400
State Factor
State Equalized Value
4,200
0.060
1,400
Valuation
Fair Market Value (non-farmland)
PIN
Owner
Bill #
Taxes
Net Taxable Value
2025
2025 Real Estate Taxes (payable in 2026)
1st Installment Due 07/22/2026 for $52.92
2nd Installment Due 09/22/2026 for $52.92
* 27305*
15-16-351-001
AMEREN ILLINOIS COMPANY
C/O AMEREN SERVICES
1901 CHOUTEAU AVE MC210
P O BOX 66149
ST LOUIS, IL 63166-6149
Real Estate Tax
Drainage Tax
Total Tax Due
105.84
0.00
$105.84
"""
        result = extract_tax_bill_fields(text, include_metadata=True)
        normalized = normalize_fields("Tax Bill", result["fields"])

        self.assertEqual(result["fields"]["tax_bill_number"], "27305")
        self.assertEqual(result["fields"]["tax_year"], "2025")
        self.assertEqual(result["fields"]["parcel_id"], "15-16-351-001")
        self.assertEqual(result["fields"]["owner_name"], "AMEREN ILLINOIS COMPANY")
        self.assertEqual(normalized["assessed_value"], 1400.0)
        self.assertEqual(normalized["taxable_value"], 1400.0)
        self.assertEqual(normalized["market_value"], 4200.0)
        self.assertEqual(normalized["tax_amount"], 105.84)
        self.assertEqual(normalized["total_due"], 105.84)
        self.assertEqual(normalized["installment_1"], 52.92)
        self.assertEqual(normalized["installment_2"], 52.92)
        self.assertEqual(normalized["installment_1_due_date"], "2026-07-22")
        self.assertEqual(normalized["installment_2_due_date"], "2026-09-22")
        self.assertEqual(
            result["metadata"]["market_value"]["extraction_method"],
            "illinois_market_value_inference",
        )


if __name__ == "__main__":
    unittest.main()
