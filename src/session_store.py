from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


SCHEMA_VERSION = 1


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def document_session_path() -> Path:
    return project_root() / "data" / "document_session.json"


def empty_document_session() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "processed_documents": [],
        "audit_log": [],
        "review_queue": [],
        "exports": [],
        "duplicate_tracking": {},
        "processed_file_keys": [],
    }


def load_document_session(path: Path | None = None) -> Tuple[Dict[str, Any], str]:
    store_path = path or document_session_path()
    if not store_path.exists():
        return empty_document_session(), f"No stored document session yet. It will be created at {store_path}."
    try:
        payload = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return empty_document_session(), f"Stored document session could not be read: {exc}"

    session = empty_document_session()
    if isinstance(payload, dict):
        session.update(
            {
                "schema_version": payload.get("schema_version", SCHEMA_VERSION),
                "processed_documents": payload.get("processed_documents", []),
                "audit_log": payload.get("audit_log", []),
                "review_queue": payload.get("review_queue", []),
                "exports": payload.get("exports", []),
                "duplicate_tracking": payload.get("duplicate_tracking", {}),
                "processed_file_keys": payload.get("processed_file_keys", []),
            }
        )
    return session, f"Loaded stored document session from {store_path}."


def make_json_safe(value: Any, depth: int = 0, seen: set[int] | None = None) -> Any:
    """Return an acyclic JSON-friendly copy of nested session data."""
    if seen is None:
        seen = set()
    if depth > 20:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    value_id = id(value)
    if isinstance(value, dict):
        if value_id in seen:
            return "[circular-reference]"
        seen.add(value_id)
        safe_dict = {
            str(key): make_json_safe(item, depth + 1, seen)
            for key, item in value.items()
        }
        seen.remove(value_id)
        return safe_dict

    if isinstance(value, (list, tuple, set)):
        if value_id in seen:
            return ["[circular-reference]"]
        seen.add(value_id)
        safe_list = [make_json_safe(item, depth + 1, seen) for item in value]
        seen.remove(value_id)
        return safe_list

    return str(value)


def save_document_session(session: Dict[str, Any], path: Path | None = None) -> Tuple[bool, str]:
    store_path = path or document_session_path()
    try:
        store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = empty_document_session()
        payload.update(session)
        payload["schema_version"] = SCHEMA_VERSION
        store_path.write_text(json.dumps(make_json_safe(payload), indent=2), encoding="utf-8")
        return True, f"Document session saved to {store_path}."
    except Exception as exc:
        return False, f"Document session could not be saved: {exc}"
