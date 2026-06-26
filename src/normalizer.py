import re
from typing import Any, Dict

from dateutil import parser as date_parser

from config.document_schemas import DOCUMENT_SCHEMAS, get_field_type
from src.utils import is_blank


def normalize_amount(value: Any) -> Any:
    if is_blank(value):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    original = str(value).strip()
    negative = original.startswith("(") and original.endswith(")")
    cleaned = original.replace("$", "").replace(",", "").replace("USD", "").strip()
    typo_decimal = re.fullmatch(r"\(?-?\d{1,3}(?:,\d{3})+,\d{2}\)?", original.replace("$", "").strip())
    if typo_decimal:
        cleaned_original = original.replace("$", "").strip().strip("()")
        head, tail = cleaned_original.rsplit(",", 1)
        cleaned = head.replace(",", "") + "." + tail
    cleaned = cleaned.strip("()")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return original
    try:
        number = float(match.group(0))
        return -number if negative else number
    except ValueError:
        return original


def normalize_date(value: Any) -> Any:
    if is_blank(value):
        return ""
    original = str(value).strip()
    try:
        return date_parser.parse(original, fuzzy=True).date().isoformat()
    except Exception:
        return original


def normalize_year(value: Any) -> Any:
    if is_blank(value):
        return ""
    original = str(value).strip()
    match = re.search(r"\b(19|20)\d{2}\b", original)
    return match.group(0) if match else original


def normalize_text(value: Any) -> str:
    if is_blank(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_fields(document_class: str, extracted_fields: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    schema = DOCUMENT_SCHEMAS.get(document_class, {})
    for field_name in schema:
        value = extracted_fields.get(field_name, "")
        field_type = get_field_type(document_class, field_name)
        if field_type == "amount":
            normalized[field_name] = normalize_amount(value)
        elif field_type == "date":
            normalized[field_name] = normalize_date(value)
        elif field_type == "year":
            normalized[field_name] = normalize_year(value)
        else:
            normalized[field_name] = normalize_text(value)
    return normalized
