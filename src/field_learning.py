from __future__ import annotations

from typing import Any, Dict, List

from config.document_schemas import get_field_type
from src.extraction_engine import clean_value, extract_typed_value, normalize_label, split_document_lines
from src.normalizer import normalize_amount


def infer_label_near_value(raw_text: str, corrected_value: Any) -> str:
    """Find the nearest human-readable label for a reviewed value."""
    value = clean_value(str(corrected_value or ""))
    if not value:
        return ""
    stacked_label = infer_stacked_table_label(raw_text, value)
    if stacked_label:
        return stacked_label
    value_key = normalize_label(value)
    lines = split_document_lines(raw_text)
    for line in lines:
        if value not in line.text and value_key not in normalize_label(line.text):
            continue
        if ":" in line.text:
            label, possible_value = line.text.split(":", 1)
            if value in possible_value or value_key in normalize_label(possible_value):
                return clean_value(label)
        for previous_index in range(line.index - 1, max(-1, line.index - 4), -1):
            previous = lines[previous_index].text
            previous_label = clean_value(previous.rstrip(":"))
            normalized_previous = normalize_label(previous_label)
            if previous.endswith(":") and 1 <= len(normalized_previous.split()) <= 6:
                return previous_label
            if 1 <= len(normalized_previous.split()) <= 4 and not any(char.isdigit() for char in previous_label):
                return previous_label
    return ""


def _same_amount(left: Any, right: Any) -> bool:
    left_amount = normalize_amount(left)
    right_amount = normalize_amount(right)
    if isinstance(left_amount, (int, float)) and isinstance(right_amount, (int, float)):
        return abs(float(left_amount) - float(right_amount)) < 0.005
    return clean_value(str(left)) == clean_value(str(right))


def _is_amount_line(value: str) -> bool:
    return isinstance(normalize_amount(value), (int, float))


def infer_stacked_table_label(raw_text: str, corrected_value: Any) -> str:
    """Infer the header aligned with a value in label-block/value-block tables."""
    lines = split_document_lines(raw_text)
    for value_line in lines:
        if not _same_amount(value_line.text, corrected_value):
            continue
        amount_start = value_line.index
        while amount_start > 0 and _is_amount_line(lines[amount_start - 1].text):
            amount_start -= 1
        value_position = value_line.index - amount_start

        label_end = amount_start - 1
        while label_end >= 0 and not normalize_label(lines[label_end].text):
            label_end -= 1
        labels = []
        cursor = label_end
        while cursor >= 0:
            label_text = clean_value(lines[cursor].text)
            normalized = normalize_label(label_text)
            if not normalized or _is_amount_line(label_text):
                break
            if len(normalized.split()) > 6:
                break
            labels.append((label_text, normalized))
            cursor -= 1
            if len(labels) > 12:
                break
        labels.reverse()
        if value_position < len(labels):
            return labels[value_position][0]
    return ""


def _schema_type_to_extraction_type(document_class: str, field_name: str) -> str:
    field_type = get_field_type(document_class, field_name)
    if field_type in {"amount", "date", "year"}:
        return field_type
    if field_name.endswith("_id") or field_name.endswith("_number"):
        return "alphanumeric"
    return "text"


def _value_after_learned_label(
    raw_text: str,
    label: str,
    value_type: str,
    max_lookahead: int = 4,
) -> tuple[str, str, str, int | None, int | None]:
    wanted = normalize_label(label)
    if not wanted:
        return "", "", "", None, None
    lines = split_document_lines(raw_text)
    for line in lines:
        current = clean_value(line.text)
        inline_value = ""
        if ":" in current:
            prefix, remainder = current.split(":", 1)
            if normalize_label(prefix) == wanted:
                inline_value = clean_value(remainder)
        elif normalize_label(current.rstrip(":")) != wanted:
            continue

        if inline_value:
            typed_value = extract_typed_value(inline_value, value_type) if value_type != "text" else inline_value
            if typed_value:
                return typed_value, line.text, line.text, line.index, line.index

        for offset in range(1, max_lookahead + 1):
            next_index = line.index + offset
            if next_index >= len(lines):
                break
            next_line = lines[next_index]
            next_text = clean_value(next_line.text)
            if not next_text:
                continue
            if next_text.endswith(":") and len(normalize_label(next_text).split()) <= 6:
                break
            typed_value = extract_typed_value(next_text, value_type) if value_type != "text" else next_text
            if typed_value:
                return typed_value, line.text, next_line.text, line.index, next_line.index
    return "", "", "", None, None


def _value_from_stacked_learned_label(
    raw_text: str,
    label: str,
    value_type: str,
) -> tuple[str, str, str, int | None, int | None]:
    wanted = normalize_label(label)
    if not wanted:
        return "", "", "", None, None
    lines = split_document_lines(raw_text)
    for label_line in lines:
        if normalize_label(label_line.text) != wanted:
            continue

        labels = []
        cursor = label_line.index
        while cursor < len(lines):
            text_value = clean_value(lines[cursor].text)
            normalized = normalize_label(text_value)
            if not normalized or _is_amount_line(text_value):
                break
            if len(normalized.split()) > 6:
                break
            labels.append(lines[cursor])
            cursor += 1
            if len(labels) > 12:
                break

        amount_lines = []
        while cursor < len(lines):
            text_value = clean_value(lines[cursor].text)
            if not _is_amount_line(text_value):
                break
            amount_lines.append(lines[cursor])
            cursor += 1

        position = next((index for index, item in enumerate(labels) if item.index == label_line.index), None)
        if position is None or position >= len(amount_lines):
            continue
        amount_line = amount_lines[position]
        value = extract_typed_value(amount_line.text, value_type) if value_type != "text" else amount_line.text
        if value:
            return value, label_line.text, amount_line.text, label_line.index, amount_line.index
    return "", "", "", None, None


def apply_learned_field_aliases(
    extraction_result: Dict[str, Any],
    document_class: str,
    raw_text: str,
    learned_aliases: Dict[str, Dict[str, List[str]]] | None,
) -> Dict[str, Any]:
    """Apply reviewer-taught labels as a lightweight local extraction model."""
    class_aliases = (learned_aliases or {}).get(document_class, {})
    if not class_aliases:
        return extraction_result

    for field_name, aliases in class_aliases.items():
        current_value = clean_value(extraction_result.get("fields", {}).get(field_name, ""))
        current_confidence = float(
            extraction_result.get("metadata", {}).get(field_name, {}).get("confidence") or 0
        )
        if current_value and current_confidence >= 0.7:
            continue
        value_type = _schema_type_to_extraction_type(document_class, field_name)
        for alias in aliases:
            value, label_line, value_line, label_index, value_index = _value_after_learned_label(
                raw_text,
                alias,
                value_type,
            )
            method = "local_field_learning"
            if not value:
                value, label_line, value_line, label_index, value_index = _value_from_stacked_learned_label(
                    raw_text,
                    alias,
                    value_type,
                )
                method = "local_field_learning_stacked_table"
            if not value:
                continue
            metadata = {
                "field_name": field_name,
                "value": value,
                "confidence": 0.88,
                "source_line": label_line if label_line == value_line else f"{label_line} | {value_line}",
                "label_line": label_line,
                "value_line": value_line,
                "label_index": label_index,
                "value_index": value_index,
                "extraction_method": method,
                "score": 0.88,
                "reasons": [
                    "reviewer_taught_label",
                    f"learned_alias={alias}",
                ],
            }
            extraction_result.setdefault("fields", {})[field_name] = value
            extraction_result.setdefault("metadata", {})[field_name] = metadata
            extraction_result.setdefault("candidates", {}).setdefault(field_name, []).insert(0, metadata)
            break
    return extraction_result
