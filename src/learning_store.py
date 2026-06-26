from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


SCHEMA_VERSION = 1


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def learning_store_path() -> Path:
    return project_root() / "data" / "learning_store.json"


def empty_learning_store() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "class_training_examples": [],
        "field_training_examples": [],
        "learned_field_aliases": {},
        "review_training_events": [],
        "model_version": 1,
    }


def load_learning_store(path: Path | None = None) -> Tuple[Dict[str, Any], str]:
    store_path = path or learning_store_path()
    if not store_path.exists():
        return empty_learning_store(), f"No stored learning file yet. It will be created at {store_path}."
    try:
        payload = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return empty_learning_store(), f"Stored learning file could not be read: {exc}"

    store = empty_learning_store()
    if isinstance(payload, dict):
        store.update(
            {
                "schema_version": payload.get("schema_version", SCHEMA_VERSION),
                "class_training_examples": payload.get("class_training_examples", []),
                "field_training_examples": payload.get("field_training_examples", []),
                "learned_field_aliases": payload.get("learned_field_aliases", {}),
                "review_training_events": payload.get("review_training_events", []),
                "model_version": payload.get("model_version", 1),
            }
        )
    return store, f"Loaded stored learning data from {store_path}."


def save_learning_store(store: Dict[str, Any], path: Path | None = None) -> Tuple[bool, str]:
    store_path = path or learning_store_path()
    try:
        store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = empty_learning_store()
        payload.update(store)
        payload["schema_version"] = SCHEMA_VERSION
        store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True, f"Learning data saved to {store_path}."
    except Exception as exc:
        return False, f"Learning data could not be saved: {exc}"
