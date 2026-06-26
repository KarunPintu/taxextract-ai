from typing import Any, Dict, Iterable, List

from config.validation_config import CLASSIFICATION_REVIEW_THRESHOLD, OCR_CONFIDENCE_REVIEW_THRESHOLD
from config.document_schemas import get_required_fields
from src.insights import generate_document_insights
from src.normalizer import normalize_fields
from src.utils import add_audit_event, is_blank, now_iso
from src.validator import summarize_validation_status, validate_document


def get_review_reasons(document: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    if document.get("manual_review_requested"):
        reasons.append("Manually marked for review")
    if document.get("document_class") == "Unknown":
        reasons.append("Document class is unknown")
    if int(document.get("classification_confidence") or 0) < CLASSIFICATION_REVIEW_THRESHOLD:
        reasons.append("Classification confidence is low")

    ocr = document.get("ocr", {})
    if ocr.get("required") and not ocr.get("available"):
        reasons.append("OCR engine is not available")
    if ocr.get("confidence") is not None and float(ocr["confidence"]) < OCR_CONFIDENCE_REVIEW_THRESHOLD:
        reasons.append("OCR confidence is low")

    for result in document.get("validation_results", []):
        if result.get("status") == "failed":
            reasons.append(result.get("message", "Validation failed"))
        elif result.get("status") == "warning":
            reasons.append(result.get("message", "Validation warning"))

    required_fields = get_required_fields(document.get("document_class", "Unknown"))
    metadata = document.get("extraction_metadata", {})
    for field_name in required_fields:
        confidence = float(metadata.get(field_name, {}).get("confidence") or 0)
        if confidence and confidence < 0.58:
            reasons.append(f"Low extraction confidence for {field_name}")
    return list(dict.fromkeys(reasons))


def document_needs_review(document: Dict[str, Any]) -> bool:
    return bool(get_review_reasons(document))


def build_review_queue(documents: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        document
        for document in documents
        if document.get("review_status") in ["Needs Review", "Follow-up"] or document_needs_review(document)
    ]


def apply_field_corrections(
    document: Dict[str, Any],
    reviewed_fields: Dict[str, Any],
    existing_documents: Iterable[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    document["reviewed_fields"] = reviewed_fields
    document["normalized_fields"] = normalize_fields(document.get("document_class", "Unknown"), reviewed_fields)
    document["validation_results"] = validate_document(
        document.get("document_class", "Unknown"),
        document["normalized_fields"],
        existing_documents=existing_documents,
        current_document_id=document.get("document_id", ""),
    )
    document["validation_status"] = summarize_validation_status(document["validation_results"])
    document["insights"] = generate_document_insights(document)
    document["processed_at"] = now_iso()
    add_audit_event(document, "Field Corrections Saved", "Reviewer saved corrected field values.")
    return document


def apply_reviewer_action(
    document: Dict[str, Any],
    action: str,
    reviewer_name: str = "",
    override_reason: str = "",
    comments: str = "",
) -> tuple[bool, str]:
    action = action.strip()
    validation_failed = document.get("validation_status") == "Failed"

    if action == "Approve" and validation_failed:
        return False, "Validation has failed. Use Approve with Override if the reviewer accepts responsibility."

    if action == "Approve with Override":
        if is_blank(reviewer_name) or is_blank(override_reason) or is_blank(comments):
            return False, "Reviewer name, override reason, and comments are required for override."
        document["review_status"] = "Approved with Override"
        document["processing_status"] = "Approved"
        document["override_details"] = {
            "override_status": "Override Applied",
            "override_reason": override_reason,
            "reviewer_name": reviewer_name,
            "reviewer_comments": comments,
            "override_timestamp": now_iso(),
        }
        add_audit_event(
            document,
            "Override Approved",
            "Reviewer approved the document with override.",
            reviewer_name=reviewer_name,
            details=document["override_details"],
        )
        document["insights"] = generate_document_insights(document)
        return True, "Document approved with override."

    if action == "Approve":
        document["review_status"] = "Approved"
        document["processing_status"] = "Approved"
        add_audit_event(document, "Approved", "Reviewer approved the document.", reviewer_name=reviewer_name)
        document["insights"] = generate_document_insights(document)
        return True, "Document approved."

    if action == "Reject":
        document["review_status"] = "Rejected"
        document["processing_status"] = "Rejected"
        add_audit_event(document, "Rejected", comments or "Reviewer rejected the document.", reviewer_name=reviewer_name)
        document["insights"] = generate_document_insights(document)
        return True, "Document rejected."

    if action == "Mark for Follow-up":
        document["review_status"] = "Follow-up"
        document["processing_status"] = "Review Required"
        add_audit_event(
            document,
            "Follow-up Required",
            comments or "Reviewer marked the document for follow-up.",
            reviewer_name=reviewer_name,
        )
        document["insights"] = generate_document_insights(document)
        return True, "Document marked for follow-up."

    return False, "Unknown reviewer action."
