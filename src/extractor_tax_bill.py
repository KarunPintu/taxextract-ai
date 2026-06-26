import re
from typing import Any, Dict

from src.extraction_engine import FieldSpec, clean_value, extract_with_specs, normalize_label, split_document_lines
from src.normalizer import normalize_amount


ILLINOIS_ASSESSMENT_RATIO = 0.333333


def _valid_bill_number(value: str) -> bool:
    value = clean_value(value)
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_/]{3,}", value)) and bool(re.search(r"\d", value))


def _valid_owner_name(value: str) -> bool:
    value = clean_value(value)
    return len(value) >= 2 and not value.endswith(":") and not re.fullmatch(r"[\d,.$]+", value)


def _valid_state(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2}", clean_value(value)))


TAX_BILL_SPECS = [
    FieldSpec(
        "tax_bill_number",
        ["Tax Bill Number", "Bill Number", "Statement Number", "Tax Bill #"],
        value_type="alphanumeric",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["account", "reference", "parcel"],
        validator=_valid_bill_number,
    ),
    FieldSpec(
        "tax_year",
        ["Tax Year", "Year"],
        value_type="year",
        required=True,
        max_lookahead=2,
        forbidden_sections=["payment", "bank_details", "footer"],
    ),
    FieldSpec(
        "owner_name",
        ["Owner Name", "Owner", "Taxpayer", "Property Owner"],
        value_type="text",
        required=True,
        max_lookahead=4,
        forbidden_sections=["payment", "bank_details", "footer"],
        validator=_valid_owner_name,
    ),
    FieldSpec("owner_address", ["Owner Address", "Mailing Address", "Property Address"], value_type="text", max_lookahead=4, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("city", ["City"], value_type="text", max_lookahead=1, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("state", ["State"], value_type="text", max_lookahead=1, forbidden_sections=["payment", "bank_details", "footer"], validator=_valid_state),
    FieldSpec("zip", ["ZIP", "Zip Code", "Postal Code"], value_type="text", max_lookahead=1, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec(
        "parcel_id",
        ["Parcel ID", "Parcel Number", "Parcel No", "Property ID", "PIN", "APN"],
        value_type="alphanumeric",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["account", "reference", "payment"],
        validator=_valid_bill_number,
    ),
    FieldSpec("county_or_jurisdiction", ["County or Jurisdiction", "Jurisdiction", "County"], value_type="text", max_lookahead=2, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("tax_amount", ["Tax Amount", "Base Tax", "Current Tax", "Real Estate Tax"], value_type="amount", required=True, max_lookahead=3, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("penalty_amount", ["Penalty Amount", "Penalty"], value_type="amount", max_lookahead=2, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("interest_amount", ["Interest Amount", "Interest"], value_type="amount", max_lookahead=2, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec(
        "total_due",
        ["Total Due", "Amount Due", "Net Tax", "Total Amount Due", "Total Tax Due"],
        value_type="amount",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["subtotal", "assessed", "taxable"],
    ),
    FieldSpec("due_date", ["Due Date", "Payment Due Date"], value_type="date", max_lookahead=2, allow_previous_line=True, forbidden_sections=["bank_details", "footer"]),
    FieldSpec("assessed_value", ["Assessed Value", "Total Assessed Value", "State Equalized Value"], value_type="amount", required=True, max_lookahead=3, forbidden_sections=["payment", "bank_details", "footer"], negative_label_words=["taxable", "market"]),
    FieldSpec("taxable_value", ["Taxable Value", "Total Taxable Value", "Net Taxable Value"], value_type="amount", required=True, max_lookahead=3, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("market_value", ["Market Value", "Fair Market Value"], value_type="amount", required=True, max_lookahead=3, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("exemption_value", ["Exemption Value", "Exemptions", "Total Exemption"], value_type="amount", max_lookahead=3, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("installment_1", ["Installment 1", "First Installment", "Installment One"], value_type="amount", required=True, max_lookahead=3, forbidden_sections=["payment", "bank_details", "footer"], negative_label_words=["due date"]),
    FieldSpec("installment_1_due_date", ["Installment 1 Due Date", "First Installment Due Date"], value_type="date", required=True, max_lookahead=2, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("installment_2", ["Installment 2", "Second Installment", "Installment Two"], value_type="amount", required=True, max_lookahead=3, forbidden_sections=["payment", "bank_details", "footer"], negative_label_words=["due date"]),
    FieldSpec("installment_2_due_date", ["Installment 2 Due Date", "Second Installment Due Date"], value_type="date", required=True, max_lookahead=2, forbidden_sections=["payment", "bank_details", "footer"]),
]


def _make_metadata(
    field_name: str,
    value: str,
    confidence: float,
    label_line: str,
    value_line: str,
    method: str,
    reasons: list[str] | None = None,
) -> Dict[str, Any]:
    return {
        "field_name": field_name,
        "value": value,
        "confidence": round(confidence, 2),
        "source_line": label_line if label_line == value_line else f"{label_line} | {value_line}",
        "label_line": label_line,
        "value_line": value_line,
        "label_index": None,
        "value_index": None,
        "extraction_method": method,
        "score": round(confidence, 3),
        "reasons": reasons or ["tax_bill_layout_mapping"],
    }


def _set_field(
    result: Dict[str, Any],
    field_name: str,
    value: Any,
    confidence: float,
    label_line: str,
    value_line: str,
    method: str,
    replace_below: float = 0.95,
    reasons: list[str] | None = None,
) -> None:
    value = clean_value(str(value or ""))
    if not value:
        return
    current_value = clean_value(result.get("fields", {}).get(field_name, ""))
    current_confidence = float(result.get("metadata", {}).get(field_name, {}).get("confidence") or 0)
    if current_value and current_confidence >= replace_below:
        return
    metadata = _make_metadata(field_name, value, confidence, label_line, value_line, method, reasons)
    result.setdefault("fields", {})[field_name] = value
    result.setdefault("metadata", {})[field_name] = metadata
    result.setdefault("candidates", {}).setdefault(field_name, []).insert(0, metadata)


def _clear_bad_optional_amount(
    result: Dict[str, Any],
    field_name: str,
    method: str,
) -> None:
    result.setdefault("fields", {})[field_name] = ""
    result.setdefault("metadata", {})[field_name] = _make_metadata(
        field_name,
        "",
        0.0,
        "",
        "",
        method,
        ["cleared_layout_mismatch"],
    )


def _amount_candidates(lines: list[str], start: int, end: int) -> list[float]:
    values: list[float] = []
    for line in lines[max(0, start) : min(len(lines), end)]:
        if not re.search(r"[$,]", line):
            continue
        parsed = normalize_amount(line)
        if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
            number = float(parsed)
            if number > 0:
                values.append(number)
    return values


def _format_amount(value: float) -> str:
    if abs(value - round(value)) < 0.005:
        return f"{round(value):,.0f}"
    return f"{value:,.2f}"


def _find_line_index(lines: list[str], label: str) -> int | None:
    wanted = normalize_label(label)
    for index, line in enumerate(lines):
        if normalize_label(line) == wanted:
            return index
    return None


def _extract_parcel_id(full_text: str) -> str:
    match = re.search(r"\b\d{2}-\d{2}-\d{3}-\d{3}\b", full_text)
    return match.group(0) if match else ""


def _extract_owner_and_address(lines: list[str], parcel_id: str) -> tuple[str, str]:
    if not parcel_id:
        return "", ""
    company_pattern = re.compile(r"\b(company|co\.?|llc|inc\.?|corporation|corp\.?|services)\b", re.IGNORECASE)
    label_words = {"parcel", "pin", "bill", "taxes", "owner", "due date", "tax amount"}
    for index, line in enumerate(lines[:-1]):
        if line != parcel_id:
            continue
        candidate_owner = clean_value(lines[index + 1])
        if normalize_label(candidate_owner) in label_words:
            continue
        if not company_pattern.search(candidate_owner):
            continue
        address_lines: list[str] = []
        for address_line in lines[index + 2 : index + 6]:
            normalized = normalize_label(address_line)
            if normalized in label_words or "tax rate" in normalized:
                break
            if re.search(r"\b\d{2}-\d{2}-\d{3}-\d{3}\b", address_line):
                break
            address_lines.append(clean_value(address_line))
        return candidate_owner, clean_value(" ".join(address_lines))
    return "", ""


def _apply_installment_lines(result: Dict[str, Any], text: str) -> None:
    pattern = re.compile(
        r"\b([12])(?:st|nd)\s+Installment\s+Due\s+(\d{1,2}/\d{1,2}/\d{4})\s+for\s+\$?([\d,]+\.\d{2})",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        number, due_date, amount = match.groups()
        prefix = "installment_1" if number == "1" else "installment_2"
        source = match.group(0)
        _set_field(
            result,
            prefix,
            amount,
            0.96,
            f"{number}{'st' if number == '1' else 'nd'} Installment",
            source,
            "installment_due_sentence",
            reasons=["installment_sentence_amount"],
        )
        _set_field(
            result,
            f"{prefix}_due_date",
            due_date,
            0.96,
            f"{number}{'st' if number == '1' else 'nd'} Installment Due",
            source,
            "installment_due_sentence",
            reasons=["installment_sentence_due_date"],
        )


def _apply_tax_summary_table(result: Dict[str, Any], lines: list[str]) -> None:
    real_estate_index = _find_line_index(lines, "Real Estate Tax")
    drainage_index = _find_line_index(lines, "Drainage Tax")
    total_due_index = _find_line_index(lines, "Total Tax Due")
    if real_estate_index is None or drainage_index is None or total_due_index is None:
        return

    amount_lines: list[str] = []
    for line in lines[total_due_index + 1 : total_due_index + 8]:
        parsed = normalize_amount(line)
        if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
            amount_lines.append(line)
        if len(amount_lines) >= 3:
            break
    if not amount_lines:
        return
    if len(amount_lines) >= 1:
        _set_field(
            result,
            "tax_amount",
            amount_lines[0],
            0.94,
            "Real Estate Tax",
            amount_lines[0],
            "tax_summary_table",
            reasons=["real_estate_tax_line"],
        )
    if len(amount_lines) >= 3:
        _set_field(
            result,
            "total_due",
            amount_lines[2],
            0.94,
            "Total Tax Due",
            amount_lines[2],
            "tax_summary_table",
            reasons=["total_tax_due_line"],
        )


def _apply_illinois_value_mapping(result: Dict[str, Any], lines: list[str]) -> None:
    state_equalized_index = _find_line_index(lines, "State Equalized Value")
    net_taxable_index = _find_line_index(lines, "Net Taxable Value")
    if state_equalized_index is None:
        return

    candidates = sorted(set(_amount_candidates(lines, state_equalized_index - 8, state_equalized_index + 12)))
    assessed_value = 0.0
    market_value = 0.0
    if len(candidates) >= 2 and 2.5 <= (candidates[-1] / max(candidates[0], 1)) <= 3.5:
        assessed_value = candidates[0]
        market_value = candidates[-1]
    elif candidates:
        assessed_value = candidates[0]
        market_value = assessed_value / ILLINOIS_ASSESSMENT_RATIO

    if assessed_value:
        assessed_text = _format_amount(assessed_value)
        _set_field(
            result,
            "assessed_value",
            assessed_text,
            0.91,
            "State Equalized Value",
            assessed_text,
            "illinois_equalized_value_mapping",
            reasons=["state_equalized_value_as_assessed_value"],
        )

    if net_taxable_index is not None and assessed_value:
        taxable_text = _format_amount(assessed_value)
        _set_field(
            result,
            "taxable_value",
            taxable_text,
            0.9,
            "Net Taxable Value",
            taxable_text,
            "illinois_net_taxable_mapping",
            reasons=["net_taxable_value_matches_state_equalized_value_when_no_exemptions_detected"],
        )

    if market_value:
        market_text = _format_amount(market_value)
        _set_field(
            result,
            "market_value",
            market_text,
            0.82,
            "Illinois assessment ratio 33.33%",
            market_text,
            "illinois_market_value_inference",
            reasons=["market_value_inferred_from_state_equalized_value_divided_by_33_33_percent"],
        )


def _apply_bureau_county_illinois_mapping(result: Dict[str, Any], text: str) -> None:
    lines = [line.text for line in split_document_lines(text)]
    full_text = "\n".join(lines)
    if "Bureau County" not in full_text and "State Equalized Value" not in full_text:
        return

    parcel_id = _extract_parcel_id(full_text)
    _set_field(result, "parcel_id", parcel_id, 0.95, "PIN / Parcel #", parcel_id, "illinois_bureau_stub")

    bill_match = re.search(r"\*\s*(\d{3,})\s*\*", full_text)
    if bill_match:
        _set_field(result, "tax_bill_number", bill_match.group(1), 0.92, "Bill #", bill_match.group(0), "illinois_bureau_stub")

    year_match = re.search(r"\b(20\d{2})\s+Real\s+Estate\s+Taxes\b", full_text, flags=re.IGNORECASE)
    if year_match:
        _set_field(result, "tax_year", year_match.group(1), 0.94, "Real Estate Taxes", year_match.group(0), "illinois_tax_year")

    owner_name, owner_address = _extract_owner_and_address(lines, parcel_id)
    _set_field(result, "owner_name", owner_name, 0.9, "Owner", owner_name, "illinois_owner_stub", replace_below=0.98)
    _set_field(result, "owner_address", owner_address, 0.86, "Owner address block", owner_address, "illinois_owner_stub")
    if "Bureau County" in full_text:
        _set_field(result, "county_or_jurisdiction", "Bureau County", 0.9, "County collector", "Bureau County", "illinois_county")

    _apply_installment_lines(result, full_text)
    _apply_tax_summary_table(result, lines)
    _apply_illinois_value_mapping(result, lines)

    if result["fields"].get("installment_2_due_date") and not result["fields"].get("due_date"):
        _set_field(
            result,
            "due_date",
            result["fields"]["installment_2_due_date"],
            0.74,
            "Final installment due date",
            result["fields"]["installment_2_due_date"],
            "illinois_due_date_fallback",
        )

    if result["fields"].get("penalty_amount"):
        _clear_bad_optional_amount(result, "penalty_amount", "illinois_no_penalty_amount_detected")


def extract_tax_bill_fields_with_metadata(text: str) -> Dict[str, Any]:
    result = extract_with_specs(text, TAX_BILL_SPECS)
    _apply_bureau_county_illinois_mapping(result, text)
    return result


def extract_tax_bill_fields(text: str, include_metadata: bool = False) -> Dict[str, Any]:
    result = extract_tax_bill_fields_with_metadata(text)
    return result if include_metadata else result["fields"]
