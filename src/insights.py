from collections import Counter, defaultdict
from typing import Any, Dict, List

from config.document_schemas import DOCUMENT_SCHEMAS, get_required_fields
from config.validation_config import CLASSIFICATION_REVIEW_THRESHOLD, OCR_CONFIDENCE_REVIEW_THRESHOLD
from src.utils import is_blank


def _missing_required_fields(document: Dict[str, Any]) -> List[str]:
    document_class = document.get("document_class", "Unknown")
    fields = document.get("normalized_fields", {})
    return [field for field in get_required_fields(document_class) if is_blank(fields.get(field))]


def _failed_rules(document: Dict[str, Any]) -> List[str]:
    return [
        result.get("rule_name", result.get("rule_id", "Validation rule"))
        for result in document.get("validation_results", [])
        if result.get("status") == "failed"
    ]


def _warning_rules(document: Dict[str, Any]) -> List[str]:
    return [
        result.get("rule_name", result.get("rule_id", "Validation rule"))
        for result in document.get("validation_results", [])
        if result.get("status") == "warning"
    ]


def _extraction_quality(document: Dict[str, Any]) -> int:
    document_class = document.get("document_class", "Unknown")
    schema = DOCUMENT_SCHEMAS.get(document_class, {})
    if not schema:
        return 0
    fields = document.get("normalized_fields", {})
    populated = sum(1 for field in schema if not is_blank(fields.get(field)))
    return round((populated / len(schema)) * 100)


def _financial_exposure(document: Dict[str, Any]) -> float:
    fields = document.get("normalized_fields", {})
    for field_name in ["total_amount", "total_due", "tax_amount", "assessed_value", "market_value"]:
        value = fields.get(field_name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return 0.0


def _validation_passed(document: Dict[str, Any]) -> bool:
    if document.get("validation_status") == "Passed":
        return True
    if document.get("validation_status") == "Failed":
        return False
    results = document.get("validation_results", [])
    return bool(results) and not any(result.get("status") == "failed" for result in results)


def _format_value(value: Any) -> str:
    if is_blank(value):
        return "not captured"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _format_money(value: float) -> str:
    return f"${value:,.2f}" if value else "not estimated"


def _field(document: Dict[str, Any], field_name: str) -> Any:
    normalized = document.get("normalized_fields", {})
    extracted = document.get("extracted_fields", {})
    return normalized.get(field_name, extracted.get(field_name, ""))


def _business_context_sentence(document: Dict[str, Any], exposure: float) -> str:
    document_class = document.get("document_class", "Unknown")
    file_name = document.get("file_name", "Document")
    if document_class == "Invoice":
        invoice_number = _field(document, "invoice_number")
        vendor = _field(document, "vendor_name")
        client = _field(document, "client_name")
        invoice_date = _field(document, "invoice_date")
        return (
            f"{file_name} appears to be invoice {_format_value(invoice_number)} from "
            f"{_format_value(vendor)} for {_format_value(client)}, dated {_format_value(invoice_date)}, "
            f"with financial exposure of {_format_money(exposure)}."
        )
    if document_class == "Assessment":
        owner = _field(document, "owner_name")
        parcel = _field(document, "parcel_id")
        year = _field(document, "assessment_year")
        assessed = _field(document, "assessed_value")
        taxable = _field(document, "taxable_value")
        return (
            f"{file_name} appears to be a {year or 'current'} assessment for "
            f"{_format_value(owner)} on parcel {_format_value(parcel)}, with assessed value "
            f"{_format_value(assessed)} and taxable value {_format_value(taxable)}."
        )
    if document_class == "Tax Bill":
        bill_number = _field(document, "tax_bill_number")
        owner = _field(document, "owner_name")
        parcel = _field(document, "parcel_id")
        total_due = _field(document, "total_due")
        due_date = _field(document, "due_date")
        return (
            f"{file_name} appears to be tax bill {_format_value(bill_number)} for "
            f"{_format_value(owner)} on parcel {_format_value(parcel)}, with total due "
            f"{_format_value(total_due)} and due date {_format_value(due_date)}."
        )
    return (
        f"{file_name} could not be mapped to a trusted business document class. "
        "A reviewer should confirm the document type before downstream processing."
    )


def _quality_sentence(
    document: Dict[str, Any],
    classification_confidence: int,
    extraction_quality: int,
    low_confidence_fields: List[str],
) -> str:
    validation_status = document.get("validation_status", "Not Run")
    review_status = document.get("review_status", "Needs Review")
    low_fields = ", ".join(field.replace("_", " ") for field in low_confidence_fields[:3])
    quality_note = (
        f"Classification confidence is {classification_confidence}% and field coverage is {extraction_quality}%, "
        f"with validation status {validation_status} and review status {review_status}."
    )
    if low_fields:
        quality_note += f" Low-confidence fields to confirm: {low_fields}."
    return quality_note


def _decision_sentence(
    missing_fields: List[str],
    failed_rules: List[str],
    warnings: List[str],
    low_confidence_fields: List[str],
    risk_level: str,
    export_readiness: str,
    suggested_action: str,
) -> str:
    blockers: List[str] = []
    if missing_fields:
        blockers.append("missing required fields: " + ", ".join(field.replace("_", " ") for field in missing_fields[:4]))
    if failed_rules:
        blockers.append("failed rules: " + "; ".join(failed_rules[:3]))
    if warnings:
        blockers.append("warnings: " + "; ".join(warnings[:3]))
    if low_confidence_fields:
        blockers.append(
            "low-confidence fields: "
            + ", ".join(field.replace("_", " ") for field in low_confidence_fields[:4])
        )
    blocker_text = "No blocking exceptions were detected." if not blockers else "Primary exception drivers are " + " | ".join(blockers) + "."
    return f"{blocker_text} Business risk is {risk_level}; export readiness is {export_readiness}. Recommended action: {suggested_action}."


def generate_document_insights(document: Dict[str, Any]) -> Dict[str, Any]:
    missing_fields = _missing_required_fields(document)
    failed_rules = _failed_rules(document)
    warnings = _warning_rules(document)
    ocr = document.get("ocr", {})
    classification_confidence = int(document.get("classification_confidence") or 0)
    extraction_quality = _extraction_quality(document)
    extraction_metadata = document.get("extraction_metadata", {})
    low_confidence_fields = [
        field_name
        for field_name, meta in extraction_metadata.items()
        if meta.get("value") and float(meta.get("confidence") or 0) < 0.58
    ]

    suggested_action = "Ready for export"
    risk_level = "Low"
    export_readiness = "Ready"
    exception_drivers: List[str] = []

    if document.get("document_class") == "Unknown" or classification_confidence < CLASSIFICATION_REVIEW_THRESHOLD:
        suggested_action = "Classification confidence is low. Please confirm document class"
        risk_level = "Medium"
        export_readiness = "Needs Review"
        exception_drivers.append("classification_confidence")
    if ocr.get("required") and not ocr.get("available"):
        suggested_action = "OCR engine is not available. Human review recommended"
        risk_level = "High"
        export_readiness = "Needs Review"
        exception_drivers.append("ocr_unavailable")
    elif ocr.get("confidence") is not None and float(ocr["confidence"]) < OCR_CONFIDENCE_REVIEW_THRESHOLD:
        suggested_action = "OCR confidence is low. Human review recommended"
        risk_level = "High"
        export_readiness = "Needs Review"
        exception_drivers.append("ocr_confidence")
    if missing_fields:
        suggested_action = f"Review missing {missing_fields[0].replace('_', ' ')}"
        risk_level = "High"
        export_readiness = "Needs Review"
        exception_drivers.append("missing_required_fields")
    if low_confidence_fields and export_readiness == "Ready":
        suggested_action = f"Review low-confidence extraction for {low_confidence_fields[0].replace('_', ' ')}"
        risk_level = "Medium"
        export_readiness = "Needs Review"
        exception_drivers.append("low_field_confidence")
    if failed_rules:
        amount_related = [rule for rule in failed_rules if "amount" in rule.lower() or "equal" in rule.lower()]
        suggested_action = (
            "Review amount mismatch before approval" if amount_related else "Review failed validation rules"
        )
        risk_level = "High"
        export_readiness = "Needs Review"
        exception_drivers.append("validation_failure")
    elif warnings and export_readiness == "Ready":
        suggested_action = "Review warning rules before final export"
        risk_level = "Medium"
        export_readiness = "Needs Review"
        exception_drivers.append("validation_warning")

    if document.get("review_status") == "Rejected":
        export_readiness = "Not Ready"
        suggested_action = "Rejected documents are not exportable"
        risk_level = "High"
    elif document.get("review_status") in ["Approved", "Approved with Override"]:
        export_readiness = "Ready"
        suggested_action = "Ready for export"

    exposure = _financial_exposure(document)
    summary = "\n\n".join(
        [
            _business_context_sentence(document, exposure),
            _quality_sentence(document, classification_confidence, extraction_quality, low_confidence_fields),
            _decision_sentence(
                missing_fields,
                failed_rules,
                warnings,
                low_confidence_fields,
                risk_level,
                export_readiness,
                suggested_action,
            ),
        ]
    )
    automation_decision = "Straight-through processing candidate"
    if export_readiness != "Ready":
        automation_decision = "Human-in-the-loop review required"
    if document.get("review_status") == "Approved with Override":
        automation_decision = "Human override approved with audit trail"

    strongest_evidence = sorted(
        [
            {
                "field": field_name,
                "value": meta.get("value", ""),
                "confidence": meta.get("confidence", 0),
                "source_line": meta.get("source_line", ""),
            }
            for field_name, meta in extraction_metadata.items()
            if meta.get("value")
        ],
        key=lambda item: item["confidence"],
        reverse=True,
    )[:5]

    control_recommendations = []
    if missing_fields:
        control_recommendations.append("Require reviewer correction for missing required fields before export.")
    if failed_rules:
        control_recommendations.append("Block straight-through processing until failed validation rules are resolved or overridden.")
    if classification_confidence < CLASSIFICATION_REVIEW_THRESHOLD:
        control_recommendations.append("Capture reviewer class feedback to improve the local ML classifier.")
    if low_confidence_fields:
        control_recommendations.append("Show source-line evidence and ask reviewer to confirm low-confidence fields.")
    if not control_recommendations:
        control_recommendations.append("Allow export after approval; keep audit evidence for downstream controls.")

    return {
        "summary": summary,
        "key_findings": [
            f"Detected class: {document.get('document_class', 'Unknown')}",
            f"Extraction quality: {extraction_quality}%",
            f"Validation status: {document.get('validation_status', 'Not Run')}",
            f"Review status: {document.get('review_status', 'Needs Review')}",
            f"Financial exposure: {_format_money(exposure)}",
        ],
        "missing_required_fields": missing_fields,
        "failed_rules": failed_rules,
        "warnings": warnings,
        "low_confidence_fields": low_confidence_fields,
        "confidence_summary": {
            "classification_confidence": classification_confidence,
            "ocr_required": bool(ocr.get("required")),
            "ocr_available": ocr.get("available"),
            "ocr_confidence": ocr.get("confidence"),
            "field_confidences": {
                field_name: meta.get("confidence", 0)
                for field_name, meta in extraction_metadata.items()
            },
        },
        "automation_decision": automation_decision,
        "exception_drivers": list(dict.fromkeys(exception_drivers)),
        "financial_exposure": exposure,
        "financial_exposure_display": f"${exposure:,.2f}" if exposure else "Not estimated",
        "evidence_trail": strongest_evidence,
        "control_recommendations": control_recommendations,
        "suggested_action": suggested_action,
        "business_risk_level": risk_level,
        "export_readiness": export_readiness,
        "extraction_quality": extraction_quality,
    }


def generate_portfolio_insights(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not documents:
        return {
            "most_common_failed_rule": "No processed documents yet",
            "documents_requiring_review": 0,
            "documents_passed_validation": 0,
            "fields_most_commonly_missing": "No missing fields yet",
            "class_with_highest_exception_rate": "No exceptions yet",
            "estimated_manual_time_saved": "0 minutes",
            "estimated_risk_avoided": "$0 in reviewed exception exposure",
            "straight_through_rate": "0%",
            "estimated_financial_exposure": "$0",
        }

    failed_rule_counter: Counter[str] = Counter()
    missing_field_counter: Counter[str] = Counter()
    class_totals: defaultdict[str, int] = defaultdict(int)
    class_exceptions: defaultdict[str, int] = defaultdict(int)
    total_exposure = 0.0
    straight_through_count = 0

    for document in documents:
        document_class = document.get("document_class", "Unknown")
        class_totals[document_class] += 1
        has_exception = document.get("review_status") in ["Needs Review", "Follow-up", "Rejected"]
        has_exception = has_exception or document.get("validation_status") in ["Failed", "Warning"]
        if has_exception:
            class_exceptions[document_class] += 1
        else:
            straight_through_count += 1
        total_exposure += _financial_exposure(document)

        for result in document.get("validation_results", []):
            if result.get("status") in ["failed", "warning"]:
                failed_rule_counter[result.get("rule_name", result.get("rule_id", "Validation rule"))] += 1
        for field_name in _missing_required_fields(document):
            missing_field_counter[field_name] += 1

    exception_rates = {
        document_class: class_exceptions[document_class] / max(total, 1)
        for document_class, total in class_totals.items()
    }
    highest_exception_class = max(exception_rates, key=exception_rates.get) if exception_rates else "None"
    review_count = sum(
        1 for document in documents if document.get("review_status") in ["Needs Review", "Follow-up"]
    )
    passed_validation_count = sum(1 for document in documents if _validation_passed(document))
    minutes_saved = int(len(documents) * 8 + max(0, len(documents) - review_count) * 4)
    risk_avoided = (sum(class_exceptions.values()) * 1250) + (len(documents) * 150)

    return {
        "most_common_failed_rule": failed_rule_counter.most_common(1)[0][0]
        if failed_rule_counter
        else "No failed rules",
        "documents_requiring_review": review_count,
        "documents_passed_validation": passed_validation_count,
        "fields_most_commonly_missing": missing_field_counter.most_common(1)[0][0]
        if missing_field_counter
        else "No missing required fields",
        "class_with_highest_exception_rate": highest_exception_class,
        "estimated_manual_time_saved": f"{minutes_saved} minutes",
        "estimated_risk_avoided": f"${risk_avoided:,.0f} in reviewed exception exposure",
        "straight_through_rate": f"{round((straight_through_count / max(len(documents), 1)) * 100)}%",
        "estimated_financial_exposure": f"${total_exposure:,.2f}",
    }
