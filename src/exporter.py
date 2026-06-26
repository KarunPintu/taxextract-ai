import json
from io import BytesIO
from typing import Any, Dict, Iterable, List

import pandas as pd

from config.document_schemas import SUPPORTED_DOCUMENT_CLASSES


def is_exportable(document: Dict[str, Any]) -> bool:
    if document.get("review_status") == "Rejected":
        return False
    if document.get("review_status") == "Approved with Override":
        return True
    if document.get("review_status") == "Approved":
        return True
    return document.get("review_status") == "Not Required" and document.get("validation_status") == "Passed"


def flatten_document_for_export(document: Dict[str, Any]) -> Dict[str, Any]:
    override = document.get("override_details", {})
    insights = document.get("insights", {})
    row = {
        "document_id": document.get("document_id", ""),
        "file_name": document.get("file_name", ""),
        "document_class": document.get("document_class", ""),
        "validation_status": document.get("validation_status", ""),
        "review_status": document.get("review_status", ""),
        "override_status": override.get("override_status", "No Override"),
        "override_reason": override.get("override_reason", ""),
        "reviewer_name": override.get("reviewer_name", ""),
        "reviewer_comments": override.get("reviewer_comments", ""),
        "insights": insights.get("summary", ""),
        "suggested_action": insights.get("suggested_action", ""),
        "business_risk_level": insights.get("business_risk_level", ""),
        "extraction_confidence_summary": json.dumps(
            {
                field_name: meta.get("confidence", 0)
                for field_name, meta in document.get("extraction_metadata", {}).items()
            },
            default=str,
        ),
        "processed_at": document.get("processed_at", ""),
    }
    row.update(document.get("normalized_fields", {}))
    return row


def export_documents_to_dataframe(documents: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    rows = [flatten_document_for_export(document) for document in documents]
    return pd.DataFrame(rows)


def export_to_csv(documents: Iterable[Dict[str, Any]]) -> bytes:
    dataframe = export_documents_to_dataframe(documents)
    return dataframe.to_csv(index=False).encode("utf-8")


def export_to_json(documents: Iterable[Dict[str, Any]]) -> bytes:
    rows = [flatten_document_for_export(document) for document in documents]
    return json.dumps(rows, indent=2, default=str).encode("utf-8")


def _validation_log(documents: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for document in documents:
        for result in document.get("validation_results", []):
            row = {"document_id": document.get("document_id", ""), "file_name": document.get("file_name", "")}
            row.update(result)
            row["field_names"] = ", ".join(result.get("field_names", []))
            rows.append(row)
    return pd.DataFrame(rows)


def _audit_log(documents: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for document in documents:
        for event in document.get("audit_events", []):
            row = dict(event)
            row["details"] = json.dumps(row.get("details", {}), default=str)
            rows.append(row)
    return pd.DataFrame(rows)


def export_to_excel(documents: Iterable[Dict[str, Any]]) -> bytes:
    documents = list(documents)
    master = export_documents_to_dataframe(documents)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        master.to_excel(writer, index=False, sheet_name="Master_Output")
        for document_class in SUPPORTED_DOCUMENT_CLASSES:
            class_docs = [document for document in documents if document.get("document_class") == document_class]
            sheet_name = document_class.replace(" ", "_")
            export_documents_to_dataframe(class_docs).to_excel(writer, index=False, sheet_name=sheet_name)
        _validation_log(documents).to_excel(writer, index=False, sheet_name="Validation_Log")
        _audit_log(documents).to_excel(writer, index=False, sheet_name="Audit_Log")
    output.seek(0)
    return output.getvalue()
