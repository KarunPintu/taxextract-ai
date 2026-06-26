import re
from typing import Any, Dict

from src.extraction_engine import FieldSpec, clean_value, extract_with_specs, split_document_lines
from src.normalizer import normalize_amount
from src.utils import is_blank


def _valid_invoice_number(value: str) -> bool:
    value = clean_value(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_/]{3,}", value):
        return False
    if not re.search(r"\d", value):
        return False
    return normalize_noise(value) not in {"invoice", "reference", "number"}


def _valid_text_name(value: str) -> bool:
    value = clean_value(value)
    if len(value) < 2:
        return False
    if re.search(r"\d{4,}", value):
        return False
    return not value.endswith(":")


def _valid_currency(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{3}", clean_value(value)))


def normalize_noise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


INVOICE_SPECS = [
    FieldSpec(
        "invoice_number",
        ["Invoice Number", "Invoice No", "Invoice #", "Inv No", "Inv #"],
        value_type="alphanumeric",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["payment", "reference", "customer", "account", "order", "date", "period", "total"],
        validator=_valid_invoice_number,
        fallback_patterns=[
            r"Invoice\s*(?:Number|No\.?|#)\s*[:#\-]?\s*\n?\s*([A-Za-z0-9][A-Za-z0-9\-_/]{3,})",
        ],
    ),
    FieldSpec(
        "invoice_date",
        ["Invoice Date", "Invoice date", "Document Date", "Date"],
        value_type="date",
        required=True,
        max_lookahead=2,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["due", "period", "billing"],
        fallback_patterns=[
            r"Invoice\s*date\s*[:#\-]?\s*\n?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})",
            r"Invoice\s*Date\s*[:#\-]?\s*\n?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
        ],
    ),
    FieldSpec(
        "vendor_name",
        ["Vendor Name", "Vendor", "Supplier", "From"],
        value_type="text",
        required=True,
        max_lookahead=4,
        forbidden_sections=["payment", "bank_details", "footer"],
        validator=_valid_text_name,
    ),
    FieldSpec(
        "client_name",
        ["Client Name", "Client", "Customer", "Customer Name", "Customer Name and Address", "Bill To", "Sold To", "To"],
        value_type="text",
        required=True,
        max_lookahead=4,
        forbidden_sections=["payment", "bank_details", "footer"],
        validator=_valid_text_name,
    ),
    FieldSpec(
        "client_address",
        ["Client Address", "Billing Address", "Bill To Address", "Customer Address"],
        value_type="text",
        max_lookahead=4,
        forbidden_sections=["payment", "bank_details", "footer"],
    ),
    FieldSpec(
        "subtotal",
        ["Subtotal", "Sub Total", "Net Amount"],
        value_type="amount",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["total due", "invoice total"],
        fallback_patterns=[r"Subtotal\s*\n?\s*([$€£]?\s*[\d,]+\.\d{2})"],
    ),
    FieldSpec(
        "tax_amount",
        ["Tax Amount", "Sales Tax", "VAT Charged", "VAT Amount", "Tax"],
        value_type="amount",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["vat id", "tax id"],
        fallback_patterns=[r"(?:Tax Amount|VAT Charged\s*\d*%?)\s*\n?\s*([$€£]?\s*[\d,]+\.\d{2})"],
    ),
    FieldSpec(
        "total_amount",
        ["Total Amount", "Invoice Total", "Total"],
        value_type="amount",
        required=True,
        max_lookahead=4,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["subtotal", "total taxable", "total assessed", "invoice no", "invoice date"],
        fallback_patterns=[r"(?:Invoice Total|Total Amount|Total)\s*\n?\s*([$€£]?\s*[\d,]+\.\d{2})"],
    ),
    FieldSpec(
        "currency",
        ["Currency", "Currenc", "Ccy"],
        value_type="text",
        max_lookahead=1,
        forbidden_sections=["payment", "bank_details", "footer"],
        validator=_valid_currency,
        fallback_patterns=[r"Amount\s*\(([A-Z]{3})\)", r"\bCurrenc(?:y)?\s*[:#\-]?\s*([A-Z]{3})\b"],
    ),
    FieldSpec(
        "due_date",
        ["Due Date", "Payment Due", "Payment Due Date"],
        value_type="date",
        max_lookahead=3,
        allow_previous_line=True,
        prefer_previous_line=True,
        forbidden_sections=["bank_details", "footer"],
        negative_label_words=["invoice"],
        fallback_patterns=[
            r"Due Date\s*[:#\-]?\s*\n?\s*([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})",
            r"([0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})\s*\n\s*Due Date\s*:",
        ],
    ),
    FieldSpec(
        "line_items",
        ["Line Items", "Items", "Description"],
        value_type="text",
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
    ),
]


def _infer_invoice_vendor(result: Dict[str, Any], text: str) -> None:
    if result["fields"].get("vendor_name"):
        return
    lines = split_document_lines(text)
    for line in lines[:80]:
        value = line.text.strip()
        lower = value.lower()
        if line.section in {"payment", "bank_details", "footer"}:
            continue
        if lower in {"invoice", "search ads"}:
            continue
        if any(stop in lower for stop in ["customer number", "invoice number", "invoice date", "billing period", "account name"]):
            continue
        if re.search(r"\b(ltd|llc|inc|limited|gmbh|corp|corporation|company)\b", value, re.IGNORECASE):
            result["fields"]["vendor_name"] = value
            result["metadata"]["vendor_name"] = {
                "field_name": "vendor_name",
                "value": value,
                "confidence": 0.72,
                "source_line": value,
                "label_line": "inferred invoice header",
                "value_line": value,
                "label_index": line.index,
                "value_index": line.index,
                "extraction_method": "header_fallback",
                "score": 0.72,
                "reasons": ["company_suffix_in_header", "before_invoice_details"],
            }
            break


def _set_inferred_field(
    result: Dict[str, Any],
    field_name: str,
    value: Any,
    confidence: float,
    source_line: str,
    method: str,
    reasons: list[str],
) -> None:
    if value is None or str(value).strip() == "":
        return
    result["fields"][field_name] = str(value)
    result["metadata"][field_name] = {
        "field_name": field_name,
        "value": str(value),
        "confidence": confidence,
        "source_line": source_line,
        "label_line": method,
        "value_line": source_line,
        "label_index": None,
        "value_index": None,
        "extraction_method": method,
        "score": confidence,
        "reasons": reasons,
    }


def _amount_from_lines(lines: list[str], start_index: int, window: int = 6) -> tuple[str, str]:
    for line in lines[start_index + 1 : start_index + 1 + window]:
        match = re.search(r"\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,4}|,\d{2})\)?", line)
        if match:
            value = match.group(0)
            if re.fullmatch(r"\(?-?\d{1,3}(?:,\d{3})+,\d{2}\)?", value):
                head, tail = value.rsplit(",", 1)
                value = head + "." + tail
            return value, line
    return "", ""


def _apply_wrapped_service_invoice_fallback(result: Dict[str, Any], text: str) -> None:
    lines = [line.text for line in split_document_lines(text)]
    normalized_lines = [re.sub(r"[^a-z0-9]+", " ", line.lower()).strip() for line in lines]

    if is_blank(result["fields"].get("subtotal")):
        for index, normalized in enumerate(normalized_lines):
            if "amount currenc" in normalized or normalized == "amount":
                value, source = _amount_from_lines(lines, index, window=8)
                if value:
                    _set_inferred_field(
                        result,
                        "subtotal",
                        value,
                        0.76,
                        f"{lines[index]} | {source}",
                        "wrapped_service_table",
                        ["amount_header_followed_by_service_row"],
                    )
                    break

    if is_blank(result["fields"].get("currency")) or not _valid_currency(str(result["fields"].get("currency", ""))):
        for index, normalized in enumerate(normalized_lines):
            if "amount currenc" in normalized or normalized == "currency":
                for line in lines[index + 1 : index + 10]:
                    match = re.fullmatch(r"[A-Z]{3}", line.strip())
                    if match:
                        _set_inferred_field(
                            result,
                            "currency",
                            match.group(0),
                            0.74,
                            f"{lines[index]} | {line}",
                            "wrapped_service_table",
                            ["currency_code_after_amount_header"],
                        )
                        break
                if not is_blank(result["fields"].get("currency")):
                    break

    if is_blank(result["fields"].get("tax_amount")):
        for index, normalized in enumerate(normalized_lines):
            if normalized.startswith("tax"):
                value, source = _amount_from_lines(lines, index, window=3)
                if value:
                    _set_inferred_field(
                        result,
                        "tax_amount",
                        value,
                        0.78,
                        f"{lines[index]} | {source}",
                        "tax_line_followup",
                        ["tax_label_followed_by_amount"],
                    )
                    break

    if is_blank(result["fields"].get("total_amount")):
        subtotal = normalize_amount(result["fields"].get("subtotal"))
        tax_amount = normalize_amount(result["fields"].get("tax_amount"))
        advance_payment = 0.0
        for index, normalized in enumerate(normalized_lines):
            if "advance payments" in normalized or "advance payment" in normalized:
                value, _source = _amount_from_lines(lines, index, window=3)
                parsed = normalize_amount(value)
                if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
                    advance_payment = float(parsed)
                break
        if isinstance(subtotal, (int, float)) and isinstance(tax_amount, (int, float)):
            total = float(subtotal) + float(tax_amount) - advance_payment
            _set_inferred_field(
                result,
                "total_amount",
                f"{total:.2f}",
                0.68,
                "subtotal + tax_amount - advance_payments",
                "computed_reconciliation",
                ["total_line_incomplete", "computed_from_valid_subtotal_tax_and_advance"],
            )


def extract_invoice_fields_with_metadata(text: str) -> Dict[str, Any]:
    result = extract_with_specs(text, INVOICE_SPECS)
    _infer_invoice_vendor(result, text)
    _apply_wrapped_service_invoice_fallback(result, text)
    return result


def extract_invoice_fields(text: str, include_metadata: bool = False) -> Dict[str, Any]:
    result = extract_invoice_fields_with_metadata(text)
    return result if include_metadata else result["fields"]
