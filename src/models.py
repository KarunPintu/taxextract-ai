from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ValidationResult:
    rule_id: str
    rule_name: str
    document_class: str
    severity: str
    status: str
    message: str
    field_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEvent:
    timestamp: str
    document_id: str
    event_type: str
    message: str
    reviewer_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def empty_override_details() -> Dict[str, Any]:
    return {
        "override_status": "No Override",
        "override_reason": "",
        "reviewer_name": "",
        "reviewer_comments": "",
        "override_timestamp": "",
    }


def create_processed_document(
    document_id: str,
    file_name: str,
    uploaded_at: str,
    file_type: str,
) -> Dict[str, Any]:
    return {
        "document_id": document_id,
        "file_name": file_name,
        "uploaded_at": uploaded_at,
        "file_type": file_type,
        "document_class": "Unknown",
        "classification_confidence": 0,
        "classification_details": {},
        "raw_text": "",
        "extracted_fields": {},
        "extraction_metadata": {},
        "extraction_candidates": {},
        "reviewed_fields": {},
        "normalized_fields": {},
        "validation_results": [],
        "insights": {},
        "processing_status": "Uploaded",
        "validation_status": "Not Run",
        "review_status": "Needs Review",
        "export_status": "Not Exported",
        "override_details": empty_override_details(),
        "audit_events": [],
        "ocr": {
            "required": False,
            "available": None,
            "confidence": None,
            "message": "",
        },
        "manual_review_requested": False,
        "manual_class_override": "",
        "processed_at": "",
        "review_minutes": None,
    }
