import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from src.models import AuditEvent


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def new_document_id(prefix: str = "DOC") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def file_fingerprint(file_name: str, file_bytes: bytes) -> str:
    digest = hashlib.sha256(file_bytes).hexdigest()[:16]
    return f"{file_name}:{len(file_bytes)}:{digest}"


def file_extension(file_name: str) -> str:
    if "." not in file_name:
        return ""
    return file_name.rsplit(".", 1)[-1].lower()


def clean_text(text: str) -> str:
    text = text or ""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def first_non_blank(values: Iterable[Any]) -> Any:
    for value in values:
        if value is not None and str(value).strip() != "":
            return value
    return ""


def is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def add_audit_event(
    document: Dict[str, Any],
    event_type: str,
    message: str,
    reviewer_name: str = "",
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    event = AuditEvent(
        timestamp=now_iso(),
        document_id=document.get("document_id", ""),
        event_type=event_type,
        message=message,
        reviewer_name=reviewer_name,
        details=details or {},
    ).to_dict()
    document.setdefault("audit_events", []).append(event)
    return event


def flatten_validation_counts(validation_results: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "failed": sum(1 for item in validation_results if item.get("status") == "failed"),
        "warning": sum(1 for item in validation_results if item.get("status") == "warning"),
        "passed": sum(1 for item in validation_results if item.get("status") == "passed"),
    }


def status_badge_html(label: str, tone: str = "neutral") -> str:
    tones = {
        "success": ("#E8F5EE", "#147A4A"),
        "warning": ("#FFF6DA", "#8A6200"),
        "danger": ("#FDECEC", "#A93434"),
        "info": ("#EAF1FB", "#1D4F91"),
        "neutral": ("#EEF2F7", "#344054"),
    }
    background, color = tones.get(tone, tones["neutral"])
    return (
        f"<span class='status-badge' style='background:{background};"
        f"color:{color};border:1px solid {color}22;'>{label}</span>"
    )


def safe_preview(text: str, limit: int = 4000) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[Preview truncated]"


def find_value_by_labels(text: str, labels: List[str]) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        compact_line = re.sub(r"\s+", " ", line)
        for label in labels:
            label_pattern = re.escape(label).replace(r"\ ", r"\s+")
            pattern = rf"(?i)(?:^|[\s|]){label_pattern}\s*(?P<separator>[:#\-])?\s*(?P<value>.*)$"
            match = re.search(pattern, compact_line)
            if not match:
                continue
            value = match.group("value").strip(" :-|")
            if value:
                return value
            if match.group("separator"):
                return ""
            if index + 1 < len(lines):
                next_line = lines[index + 1].strip(" :-|")
                if ":" in next_line and len(next_line.split(":", 1)[0].split()) <= 5:
                    return ""
                return next_line
    return ""


def find_first_regex(text: str, pattern: str) -> str:
    match = re.search(pattern, text or "", flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip()


def as_title_case(value: Any) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if value.isupper() or value.islower():
        return value.title()
    return value
