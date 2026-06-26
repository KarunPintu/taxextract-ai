import re
from typing import Any, Dict, List, Tuple

from src.extraction_engine import FieldSpec, clean_value, extract_with_specs, normalize_label, split_document_lines
from src.normalizer import normalize_amount


def _valid_parcel_id(value: str) -> bool:
    value = clean_value(value)
    compact = re.sub(r"[\s\-_/\.]", "", value)
    if len(compact) < 4 or not re.search(r"\d", compact):
        return False
    if re.fullmatch(r"(?:19|20)\d{2}", compact):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\s\-_/\.]{3,}", value))


def _valid_owner_name(value: str) -> bool:
    value = clean_value(value)
    return len(value) >= 2 and not value.endswith(":") and not re.fullmatch(r"[\d,.$]+", value)


def _valid_address(value: str) -> bool:
    value = clean_value(value)
    normalized = normalize_label(value)
    if len(value) < 5 or not normalized:
        return False
    if value.endswith(":") or re.fullmatch(r"(?:19|20)\d{2}", value):
        return False
    if re.fullmatch(r"[\d\s,.$]+", value):
        return False
    if normalized in KNOWN_ASSESSMENT_LABELS:
        return False
    return bool(re.search(r"\d", value) or re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", value))


def _valid_text_value(value: str) -> bool:
    value = clean_value(value)
    return bool(value) and not value.endswith(":") and normalize_label(value) not in KNOWN_ASSESSMENT_LABELS


KNOWN_ASSESSMENT_LABELS = {
    normalize_label(label)
    for label in [
        "record summary",
        "tax year",
        "assessment year",
        "parcel",
        "parcel id",
        "parcel number",
        "owner",
        "owner name",
        "address",
        "owner address",
        "mailing address",
        "dba address",
        "neighborhood",
        "subdivision",
        "book",
        "page",
        "lot",
        "block",
        "acreage",
        "section",
        "township",
        "range",
        "property class",
        "exempt code",
        "municipality",
        "school district",
        "key",
        "metes and bounds",
        "remarks",
        "valuation summary",
        "market information",
        "assessment value",
        "exempt value",
        "abatement",
        "penalty",
        "total taxable",
        "total improvement value",
        "total land value",
        "total market value",
        "total appraised value",
        "assessed value",
        "taxable value",
        "market value",
        "exemption value",
        "prior year total improvement value",
        "prior year total land value",
        "prior year total appraised value",
        "tax breakdown",
        "tax payment information",
        "ownership history",
        "land information",
        "building information",
        "deed information",
        "business type",
        "economic life",
        "key",
    ]
}


ASSESSMENT_SPECS = [
    FieldSpec(
        "assessment_year",
        ["Assessment Year", "Tax Year", "Year"],
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
    FieldSpec(
        "owner_address",
        ["Owner Address", "Mailing Address", "Property Address", "Situs Address", "Address"],
        value_type="text",
        max_lookahead=4,
        forbidden_sections=["payment", "bank_details", "footer"],
        validator=_valid_address,
    ),
    FieldSpec("city", ["City"], value_type="text", max_lookahead=1, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("state", ["State"], value_type="text", max_lookahead=1, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("zip", ["ZIP", "Zip Code", "Postal Code"], value_type="text", max_lookahead=1, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec(
        "parcel_id",
        ["Parcel ID", "Parcel Number", "Parcel No", "Parcel", "Property ID", "PIN", "APN"],
        value_type="alphanumeric",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["account", "reference", "payment"],
        validator=_valid_parcel_id,
    ),
    FieldSpec("county", ["County"], value_type="text", max_lookahead=2, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("acreage", ["Acreage", "Acres"], value_type="amount", max_lookahead=2, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec(
        "assessed_value",
        ["Assessed Value", "Assessment Value", "Total Assessed Value"],
        value_type="amount",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
        negative_label_words=["taxable", "market"],
    ),
    FieldSpec(
        "taxable_value",
        ["Taxable Value", "Total Taxable Value", "Total Taxable"],
        value_type="amount",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
    ),
    FieldSpec(
        "market_value",
        ["Total Market Value", "Market Value", "Fair Market Value"],
        value_type="amount",
        required=True,
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
    ),
    FieldSpec(
        "exemption_value",
        ["Exemption Value", "Exemptions", "Total Exemption", "Exempt Value"],
        value_type="amount",
        max_lookahead=3,
        forbidden_sections=["payment", "bank_details", "footer"],
    ),
    FieldSpec("notice_date", ["Notice Date", "Assessment Notice Date"], value_type="date", max_lookahead=2, forbidden_sections=["payment", "bank_details", "footer"]),
    FieldSpec("appeal_deadline", ["Appeal Deadline", "Appeal Due Date"], value_type="date", max_lookahead=2, forbidden_sections=["payment", "bank_details", "footer"]),
]


def _make_metadata(
    field_name: str,
    value: str,
    confidence: float,
    label_line: str,
    value_line: str,
    method: str,
    label_index: int | None = None,
    value_index: int | None = None,
    reasons: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "field_name": field_name,
        "value": value,
        "confidence": round(confidence, 2),
        "source_line": label_line if label_line == value_line else f"{label_line} | {value_line}",
        "label_line": label_line,
        "value_line": value_line,
        "label_index": label_index,
        "value_index": value_index,
        "extraction_method": method,
        "score": round(confidence, 3),
        "reasons": reasons or ["assessment_specific_mapping"],
    }


def _set_field(
    result: Dict[str, Any],
    field_name: str,
    value: str,
    confidence: float,
    label_line: str,
    value_line: str,
    method: str,
    label_index: int | None = None,
    value_index: int | None = None,
    replace_below: float = 0.88,
    validator=None,
    reasons: List[str] | None = None,
) -> None:
    value = clean_value(value)
    if not value:
        return
    if validator and not validator(value):
        return
    existing = clean_value(result["fields"].get(field_name, ""))
    existing_confidence = float(result["metadata"].get(field_name, {}).get("confidence") or 0)
    existing_is_valid = True if not validator or not existing else validator(existing)
    if existing and existing_confidence >= replace_below and existing_is_valid:
        return

    result["fields"][field_name] = value
    result["metadata"][field_name] = _make_metadata(
        field_name,
        value,
        confidence,
        label_line,
        value_line,
        method,
        label_index=label_index,
        value_index=value_index,
        reasons=reasons,
    )
    result.setdefault("candidates", {}).setdefault(field_name, []).insert(0, result["metadata"][field_name])


def _line_matches_label(line_text: str, labels: List[str]) -> Tuple[bool, str, str]:
    text = clean_value(line_text)
    for label in labels:
        wanted = normalize_label(label)
        if not wanted:
            continue
        if ":" in text:
            prefix, remainder = text.split(":", 1)
            if normalize_label(prefix) == wanted:
                return True, label, clean_value(remainder)
        if normalize_label(text.rstrip(":")) == wanted:
            return True, label, ""
    return False, "", ""


def _looks_like_assessment_label(text: str) -> bool:
    normalized = normalize_label(text)
    if not normalized:
        return False
    if normalized in KNOWN_ASSESSMENT_LABELS:
        return True
    return text.strip().endswith(":") and len(normalized.split()) <= 5


def _value_after_label(
    text: str,
    labels: List[str],
    max_lookahead: int = 4,
    multiline: bool = False,
    validator=None,
) -> Tuple[str, str, str, int | None, int | None]:
    lines = split_document_lines(text)
    for line in lines:
        matched, matched_label, inline_value = _line_matches_label(line.text, labels)
        if not matched:
            continue
        if inline_value and (not validator or validator(inline_value)):
            return inline_value, line.text, line.text, line.index, line.index

        values: List[str] = []
        value_index: int | None = None
        for offset in range(1, max_lookahead + 1):
            next_index = line.index + offset
            if next_index >= len(lines):
                break
            next_line = lines[next_index]
            candidate = clean_value(next_line.text)
            if _looks_like_assessment_label(candidate):
                break
            if not candidate:
                continue
            if multiline:
                values.append(candidate)
                value_index = next_line.index if value_index is None else value_index
                continue
            if not validator or validator(candidate):
                return candidate, line.text, next_line.text, line.index, next_line.index

        if multiline and values:
            combined = clean_value(" ".join(values))
            if not validator or validator(combined):
                return combined, line.text, " | ".join(values), line.index, value_index
    return "", "", "", None, None


def _amount_after_label(text: str, labels: List[str]) -> Tuple[str, str, str, int | None, int | None]:
    raw_value, label_line, value_line, label_index, value_index = _value_after_label(
        text,
        labels,
        max_lookahead=2,
        validator=lambda value: isinstance(normalize_amount(value), (int, float)),
    )
    return raw_value, label_line, value_line, label_index, value_index


def _apply_record_summary_mapping(result: Dict[str, Any], text: str) -> None:
    field_plan = [
        ("assessment_year", ["Tax Year", "Assessment Year"], 0.94, False, None),
        ("parcel_id", ["Parcel", "Parcel ID", "Parcel Number"], 0.94, False, _valid_parcel_id),
        ("owner_name", ["Owner", "Owner Name", "Property Owner"], 0.92, False, _valid_owner_name),
        ("owner_address", ["Address", "Owner Address", "Mailing Address"], 0.9, True, _valid_address),
        ("acreage", ["Acreage", "Acres"], 0.9, False, lambda value: isinstance(normalize_amount(value), (int, float))),
    ]
    for field_name, labels, confidence, multiline, validator in field_plan:
        value, label_line, value_line, label_index, value_index = _value_after_label(
            text,
            labels,
            max_lookahead=4,
            multiline=multiline,
            validator=validator,
        )
        _set_field(
            result,
            field_name,
            value,
            confidence,
            label_line,
            value_line,
            "assessment_record_summary",
            label_index=label_index,
            value_index=value_index,
            validator=validator,
            replace_below=0.96,
        )


def _apply_valuation_summary_mapping(result: Dict[str, Any], text: str) -> None:
    value_plan = [
        ("market_value", ["Total Market Value", "Market Value"], 0.92),
        ("assessed_value", ["Assessed Value"], 0.92),
        ("taxable_value", ["Taxable Value", "Total Taxable Value"], 0.9),
        ("exemption_value", ["Exemption Value", "Total Exemption Value"], 0.84),
    ]
    for field_name, labels, confidence in value_plan:
        value, label_line, value_line, label_index, value_index = _amount_after_label(text, labels)
        _set_field(
            result,
            field_name,
            value,
            confidence,
            label_line,
            value_line,
            "assessment_valuation_summary",
            label_index=label_index,
            value_index=value_index,
            replace_below=0.96,
            reasons=["exact_valuation_summary_label"],
        )

    if not result["fields"].get("market_value"):
        value, label_line, value_line, label_index, value_index = _amount_after_label(
            text,
            ["Total Appraised Value", "Appraised Value"],
        )
        _set_field(
            result,
            "market_value",
            value,
            0.82,
            label_line,
            value_line,
            "assessment_appraised_value_fallback",
            label_index=label_index,
            value_index=value_index,
            reasons=["market_value_fell_back_to_appraised_value"],
        )

    if result["fields"].get("assessed_value") and not result["fields"].get("taxable_value"):
        assessed_value = result["fields"]["assessed_value"]
        assessed_meta = result["metadata"].get("assessed_value", {})
        _set_field(
            result,
            "taxable_value",
            assessed_value,
            0.66,
            assessed_meta.get("label_line", "Assessed Value"),
            assessed_meta.get("value_line", assessed_value),
            "assessment_taxable_inferred_from_assessed",
            label_index=assessed_meta.get("label_index"),
            value_index=assessed_meta.get("value_index"),
            replace_below=0.9,
            reasons=[
                "taxable_value_label_not_found",
                "taxable_value_inferred_from_assessed_value_for_reviewable_local_demo",
            ],
        )


def _is_amount_like(value: str) -> bool:
    return isinstance(normalize_amount(value), (int, float))


def _apply_personal_property_market_mapping(result: Dict[str, Any], text: str) -> None:
    lines = split_document_lines(text)
    label_to_field = {
        "market value": ("market_value", 0.93),
        "assessment value": ("assessed_value", 0.93),
        "assessed value": ("assessed_value", 0.93),
        "total taxable": ("taxable_value", 0.93),
        "taxable value": ("taxable_value", 0.93),
        "exempt value": ("exemption_value", 0.88),
        "exemption value": ("exemption_value", 0.88),
    }

    for line in lines:
        if normalize_label(line.text) != "market information":
            continue

        labels: List[Tuple[str, int, str]] = []
        values: List[Tuple[str, int, str]] = []
        for candidate in lines[line.index + 1 : line.index + 18]:
            text_value = clean_value(candidate.text)
            if not text_value:
                continue
            if _is_amount_like(text_value):
                values.append((text_value, candidate.index, candidate.text))
                continue
            if values:
                break
            labels.append((normalize_label(text_value), candidate.index, candidate.text))

        if not labels or not values:
            continue

        for position, (label_key, label_index, label_text) in enumerate(labels):
            mapping = label_to_field.get(label_key)
            if not mapping or position >= len(values):
                continue
            field_name, confidence = mapping
            value, value_index, value_line = values[position]
            _set_field(
                result,
                field_name,
                value,
                confidence,
                label_text,
                value_line,
                "assessment_market_information_table",
                label_index=label_index,
                value_index=value_index,
                replace_below=0.97,
                reasons=[
                    "personal_property_market_information_table",
                    f"label_position={position}",
                ],
            )
        break


def _apply_assessment_specific_mapping(result: Dict[str, Any], text: str) -> None:
    _apply_record_summary_mapping(result, text)
    _apply_valuation_summary_mapping(result, text)
    _apply_personal_property_market_mapping(result, text)


def extract_assessment_fields_with_metadata(text: str) -> Dict[str, Any]:
    result = extract_with_specs(text, ASSESSMENT_SPECS)
    _apply_assessment_specific_mapping(result, text)
    return result


def extract_assessment_fields(text: str, include_metadata: bool = False) -> Dict[str, Any]:
    result = extract_assessment_fields_with_metadata(text)
    return result if include_metadata else result["fields"]
