import re
from datetime import date
from typing import Any, Dict, Iterable, List

from dateutil import parser as date_parser

from config.document_schemas import DOCUMENT_SCHEMAS, get_required_fields
from config.validation_config import AMOUNT_TOLERANCE
from src.models import ValidationResult
from src.normalizer import normalize_amount
from src.utils import is_blank


def _result(
    rule_id: str,
    rule_name: str,
    document_class: str,
    severity: str,
    status: str,
    message: str,
    field_names: List[str],
) -> Dict[str, Any]:
    return ValidationResult(
        rule_id=rule_id,
        rule_name=rule_name,
        document_class=document_class,
        severity=severity,
        status=status,
        message=message,
        field_names=field_names,
    ).to_dict()


def _number(value: Any) -> float | None:
    if is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    normalized = normalize_amount(value)
    if isinstance(normalized, (int, float)) and not isinstance(normalized, bool):
        return float(normalized)
    return None


def _date(value: Any) -> date | None:
    if is_blank(value):
        return None
    try:
        return date_parser.parse(str(value), fuzzy=True).date()
    except Exception:
        return None


def _required_rules(document_class: str, fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    for field_name in get_required_fields(document_class):
        passed = not is_blank(fields.get(field_name))
        results.append(
            _result(
                f"{document_class.lower().replace(' ', '_')}_required_{field_name}",
                f"{field_name} must not be blank",
                document_class,
                "error",
                "passed" if passed else "failed",
                f"{field_name} is present." if passed else f"{field_name} is missing.",
                [field_name],
            )
        )
    return results


def _numeric_rule(document_class: str, fields: Dict[str, Any], field_name: str) -> Dict[str, Any]:
    value = fields.get(field_name)
    passed = _number(value) is not None
    return _result(
        f"{document_class.lower().replace(' ', '_')}_numeric_{field_name}",
        f"{field_name} must be numeric",
        document_class,
        "error",
        "passed" if passed else "failed",
        f"{field_name} is numeric." if passed else f"{field_name} must be numeric.",
        [field_name],
    )


def _year_rule(document_class: str, fields: Dict[str, Any], field_name: str) -> Dict[str, Any]:
    value = str(fields.get(field_name, "")).strip()
    passed = bool(re.fullmatch(r"\d{4}", value))
    return _result(
        f"{document_class.lower().replace(' ', '_')}_year_{field_name}",
        f"{field_name} should be a 4-digit year",
        document_class,
        "error",
        "passed" if passed else "failed",
        f"{field_name} is a valid year." if passed else f"{field_name} should be a 4-digit year.",
        [field_name],
    )


def _amount_sum_rule(
    document_class: str,
    fields: Dict[str, Any],
    left_field: str,
    right_field: str,
    total_field: str,
    rule_id: str,
    rule_name: str,
    required_when_present: bool = False,
) -> Dict[str, Any]:
    left = _number(fields.get(left_field))
    right = _number(fields.get(right_field))
    total = _number(fields.get(total_field))
    if required_when_present and is_blank(fields.get(left_field)):
        return _result(
            rule_id,
            rule_name,
            document_class,
            "info",
            "passed",
            f"{left_field} is not present, so this relationship was not required.",
            [left_field, right_field, total_field],
        )
    if left is None or right is None or total is None:
        return _result(
            rule_id,
            rule_name,
            document_class,
            "warning",
            "warning",
            "Amount relationship could not be fully validated because one value is missing or not numeric.",
            [left_field, right_field, total_field],
        )
    passed = abs((left + right) - total) <= AMOUNT_TOLERANCE
    return _result(
        rule_id,
        rule_name,
        document_class,
        "error",
        "passed" if passed else "failed",
        (
            f"{left_field} + {right_field} equals {total_field}."
            if passed
            else f"{left_field} + {right_field} does not equal {total_field}."
        ),
        [left_field, right_field, total_field],
    )


def _less_equal_rule(
    document_class: str,
    fields: Dict[str, Any],
    left_field: str,
    right_field: str,
    rule_id: str,
    rule_name: str,
) -> Dict[str, Any]:
    left = _number(fields.get(left_field))
    right = _number(fields.get(right_field))
    if left is None or right is None:
        return _result(
            rule_id,
            rule_name,
            document_class,
            "warning",
            "warning",
            "Comparison could not be fully validated because one value is missing or not numeric.",
            [left_field, right_field],
        )
    passed = left <= right + AMOUNT_TOLERANCE
    return _result(
        rule_id,
        rule_name,
        document_class,
        "error",
        "passed" if passed else "failed",
        (
            f"{left_field} is less than or equal to {right_field}."
            if passed
            else f"{left_field} should be less than or equal to {right_field}."
        ),
        [left_field, right_field],
    )


def _date_order_rule(
    document_class: str,
    fields: Dict[str, Any],
    start_field: str,
    end_field: str,
    rule_id: str,
    rule_name: str,
) -> Dict[str, Any]:
    if is_blank(fields.get(start_field)) or is_blank(fields.get(end_field)):
        return _result(
            rule_id,
            rule_name,
            document_class,
            "info",
            "passed",
            "Date comparison not required because one date is blank.",
            [start_field, end_field],
        )
    start = _date(fields.get(start_field))
    end = _date(fields.get(end_field))
    if start is None or end is None:
        return _result(
            rule_id,
            rule_name,
            document_class,
            "warning",
            "warning",
            "Date comparison could not be fully validated.",
            [start_field, end_field],
        )
    passed = end >= start
    return _result(
        rule_id,
        rule_name,
        document_class,
        "error",
        "passed" if passed else "failed",
        (
            f"{end_field} is not before {start_field}."
            if passed
            else f"{end_field} should not be before {start_field}."
        ),
        [start_field, end_field],
    )


def _duplicate_rule(
    document_class: str,
    fields: Dict[str, Any],
    existing_documents: Iterable[Dict[str, Any]] | None,
    current_document_id: str,
    key_fields: List[str],
    rule_id: str,
    rule_name: str,
) -> Dict[str, Any]:
    current_key = tuple(str(fields.get(field, "")).strip().lower() for field in key_fields)
    if any(is_blank(value) for value in current_key):
        return _result(
            rule_id,
            rule_name,
            document_class,
            "info",
            "passed",
            "Duplicate check skipped because the duplicate key is incomplete.",
            key_fields,
        )

    for document in existing_documents or []:
        if document.get("document_id") == current_document_id:
            continue
        if document.get("document_class") != document_class:
            continue
        other_fields = document.get("normalized_fields", {})
        other_key = tuple(str(other_fields.get(field, "")).strip().lower() for field in key_fields)
        if current_key == other_key:
            return _result(
                rule_id,
                rule_name,
                document_class,
                "warning",
                "warning",
                f"Possible duplicate detected against {document.get('document_id')}.",
                key_fields,
            )

    return _result(
        rule_id,
        rule_name,
        document_class,
        "info",
        "passed",
        "No duplicate was detected.",
        key_fields,
    )


def validate_document(
    document_class: str,
    fields: Dict[str, Any],
    existing_documents: Iterable[Dict[str, Any]] | None = None,
    current_document_id: str = "",
) -> List[Dict[str, Any]]:
    if document_class not in DOCUMENT_SCHEMAS:
        return [
            _result(
                "unknown_document_class",
                "Document class must be recognized",
                document_class,
                "error",
                "failed",
                "Document class is unknown. Please classify the document before export.",
                ["document_class"],
            )
        ]

    results: List[Dict[str, Any]] = []
    results.extend(_required_rules(document_class, fields))

    if document_class == "Invoice":
        for field_name in ["subtotal", "tax_amount", "total_amount"]:
            results.append(_numeric_rule(document_class, fields, field_name))
        results.append(
            _amount_sum_rule(
                document_class,
                fields,
                "subtotal",
                "tax_amount",
                "total_amount",
                "invoice_amount_reconciliation",
                "subtotal + tax_amount should equal total_amount",
            )
        )
        results.append(
            _date_order_rule(
                document_class,
                fields,
                "invoice_date",
                "due_date",
                "invoice_due_date_order",
                "due_date should not be before invoice_date",
            )
        )
        results.append(
            _duplicate_rule(
                document_class,
                fields,
                existing_documents,
                current_document_id,
                ["invoice_number"],
                "invoice_duplicate_invoice_number",
                "duplicate invoice_number should be flagged",
            )
        )

    elif document_class == "Assessment":
        results.append(_year_rule(document_class, fields, "assessment_year"))
        for field_name in ["assessed_value", "taxable_value", "market_value"]:
            results.append(_numeric_rule(document_class, fields, field_name))
        results.append(
            _less_equal_rule(
                document_class,
                fields,
                "taxable_value",
                "assessed_value",
                "assessment_taxable_le_assessed",
                "taxable_value should be less than or equal to assessed_value",
            )
        )
        results.append(
            _less_equal_rule(
                document_class,
                fields,
                "assessed_value",
                "market_value",
                "assessment_assessed_le_market",
                "assessed_value should be less than or equal to market_value",
            )
        )
        results.append(
            _amount_sum_rule(
                document_class,
                fields,
                "exemption_value",
                "taxable_value",
                "assessed_value",
                "assessment_exemption_reconciliation",
                "exemption_value + taxable_value should equal assessed_value",
                required_when_present=True,
            )
        )
        results.append(
            _date_order_rule(
                document_class,
                fields,
                "notice_date",
                "appeal_deadline",
                "assessment_appeal_deadline_order",
                "appeal_deadline should not be before notice_date",
            )
        )
        results.append(
            _duplicate_rule(
                document_class,
                fields,
                existing_documents,
                current_document_id,
                ["parcel_id", "assessment_year"],
                "assessment_duplicate_parcel_year",
                "duplicate parcel_id + assessment_year should be flagged",
            )
        )

    elif document_class == "Tax Bill":
        results.append(_year_rule(document_class, fields, "tax_year"))
        for field_name in ["tax_amount", "total_due", "assessed_value", "taxable_value", "market_value"]:
            results.append(_numeric_rule(document_class, fields, field_name))
        results.append(
            _less_equal_rule(
                document_class,
                fields,
                "taxable_value",
                "assessed_value",
                "tax_bill_taxable_le_assessed",
                "taxable_value should be less than or equal to assessed_value",
            )
        )
        results.append(
            _less_equal_rule(
                document_class,
                fields,
                "assessed_value",
                "market_value",
                "tax_bill_assessed_le_market",
                "assessed_value should be less than or equal to market_value",
            )
        )
        results.append(
            _amount_sum_rule(
                document_class,
                fields,
                "exemption_value",
                "taxable_value",
                "assessed_value",
                "tax_bill_exemption_reconciliation",
                "exemption_value + taxable_value should equal assessed_value",
                required_when_present=True,
            )
        )
        results.append(
            _amount_sum_rule(
                document_class,
                fields,
                "installment_1",
                "installment_2",
                "total_due",
                "tax_bill_installment_reconciliation",
                "installment_1 + installment_2 should equal total_due",
            )
        )
        results.append(
            _duplicate_rule(
                document_class,
                fields,
                existing_documents,
                current_document_id,
                ["parcel_id", "tax_year"],
                "tax_bill_duplicate_parcel_year",
                "duplicate parcel_id + tax_year should be flagged",
            )
        )

    return results


def summarize_validation_status(validation_results: List[Dict[str, Any]]) -> str:
    if not validation_results:
        return "Not Run"
    if any(result.get("status") == "failed" for result in validation_results):
        return "Failed"
    if any(result.get("status") == "warning" for result in validation_results):
        return "Warning"
    return "Passed"
