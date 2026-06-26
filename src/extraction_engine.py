import difflib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List

from dateutil import parser as date_parser

from src.normalizer import normalize_amount


AMOUNT_RE = re.compile(r"(?<![A-Z0-9])(?:[$€£]\s*)?\(?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?(?![A-Z0-9])")
AMOUNT_RE = re.compile(
    r"(?<![A-Z0-9])(?:[$]\s*)?\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,4}|,\d{2})\)?(?![A-Z0-9])"
)
DATE_RE = re.compile(
    r"\b(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4})\b"
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
ALNUM_ID_RE = re.compile(r"\b(?=[A-Z0-9/_-]{4,}\b)(?=.*\d)[A-Z0-9][A-Z0-9/_-]{3,}\b", re.IGNORECASE)

BAD_VALUE_WORDS = {
    "invoice",
    "assessment",
    "tax bill",
    "total",
    "subtotal",
    "date",
    "number",
    "reference",
    "client",
    "customer",
    "vendor",
    "owner",
    "parcel",
    "amount",
}

SECTION_KEYWORDS = {
    "payment": [
        "payment reference",
        "wire transfer",
        "ach",
        "payment terms",
        "please note payment",
    ],
    "bank_details": [
        "iban",
        "swift",
        "account number",
        "account name",
        "bank :",
        "bank:",
        "routing",
        "wire transfer",
    ],
    "footer": [
        "page ",
        "terms and conditions",
        "please note",
        "apple will not be able",
        "article 44",
    ],
}


@dataclass
class DocumentLine:
    index: int
    text: str
    section: str = "body"


@dataclass
class FieldSpec:
    field_name: str
    labels: List[str]
    value_type: str = "text"
    required: bool = False
    max_lookahead: int = 3
    allow_previous_line: bool = False
    prefer_previous_line: bool = False
    forbidden_sections: List[str] = field(default_factory=lambda: ["bank_details", "footer"])
    preferred_sections: List[str] = field(default_factory=list)
    negative_label_words: List[str] = field(default_factory=list)
    fallback_patterns: List[str] = field(default_factory=list)
    validator: Callable[[str], bool] | None = None


@dataclass
class ExtractionCandidate:
    field_name: str
    value: str
    confidence: float
    source_line: str
    label_line: str
    value_line: str
    label_index: int
    value_index: int
    extraction_method: str
    score: float
    reasons: List[str] = field(default_factory=list)

    def to_metadata(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["confidence"] = round(float(payload["confidence"]), 2)
        payload["score"] = round(float(payload["score"]), 3)
        return payload


def normalize_label(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text or "").lower()
    return re.sub(r"\s+", " ", text).strip()


def split_document_lines(text: str) -> List[DocumentLine]:
    lines: List[DocumentLine] = []
    active_section = "body"
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        direct_section = detect_section(line)
        if direct_section in ["payment", "bank_details"]:
            active_section = direct_section
        elif active_section in ["payment", "bank_details"] and looks_like_business_label(line):
            active_section = "body"
        section = direct_section if direct_section == "footer" else active_section
        lines.append(DocumentLine(index=len(lines), text=line, section=section))
    return lines


def detect_section(line: str) -> str:
    normalized = normalize_label(line)
    raw = line.lower()
    if re.fullmatch(r"page\s+\d+\s*/\s*\d+", raw.strip()):
        return "footer"
    for section, keywords in SECTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in raw or keyword in normalized:
                return section
    return "body"


def looks_like_business_label(line: str) -> bool:
    stripped = line.strip()
    if DATE_RE.fullmatch(stripped):
        return False
    if AMOUNT_RE.fullmatch(stripped):
        return False
    if re.fullmatch(r"(?=.*\d)[A-Za-z0-9/_-]{4,}", stripped):
        return False
    if stripped.endswith(":"):
        return True
    if " : " in stripped:
        return True
    labelish = normalize_label(stripped)
    return bool(labelish) and len(labelish.split()) <= 5 and not contains_amount(stripped)


def clean_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    value = value.strip(" :|?")
    return value


def line_without_label(line: str, label: str) -> str:
    label_tokens = normalize_label(label).split()
    if not label_tokens:
        return ""
    pattern = r"\b" + r"\s+".join(re.escape(token) for token in label_tokens) + r"\b"
    match = re.search(pattern, line, flags=re.IGNORECASE)
    if not match:
        return ""
    remainder = line[match.end() :]
    remainder = re.sub(r"^(?:\s*(?:[:#\-]|no\.?|number)\s*)+", "", remainder, flags=re.IGNORECASE)
    return clean_value(remainder)


def label_similarity(line: str, label: str) -> float:
    line_label = normalize_label(strip_likely_value(line))
    wanted = normalize_label(label)
    if not line_label or not wanted:
        return 0.0
    if line_label == wanted:
        return 1.0
    if line_label.startswith(f"{wanted} ") or wanted.startswith(f"{line_label} "):
        return 0.92
    line_tokens = set(line_label.split())
    wanted_tokens = set(wanted.split())
    if wanted_tokens and wanted_tokens.issubset(line_tokens):
        if len(wanted_tokens) == 1 and len(line_tokens) > 1:
            return 0.62
        return 0.86
    if line_tokens and line_tokens.issubset(wanted_tokens):
        if len(line_tokens) == 1 and len(wanted_tokens) > 1:
            return 0.62
        return 0.82
    return difflib.SequenceMatcher(None, line_label, wanted).ratio()


def strip_likely_value(line: str) -> str:
    if ":" in line:
        return line.split(":", 1)[0]
    if " - " in line:
        return line.split(" - ", 1)[0]
    return line


def best_label_match(line: str, spec: FieldSpec) -> tuple[str, float]:
    best_label = ""
    best_score = 0.0
    normalized_line = normalize_label(strip_likely_value(line))
    if any(word in normalized_line for word in spec.negative_label_words):
        return "", 0.0
    for label in spec.labels:
        score = label_similarity(line, label)
        if score > best_score:
            best_label = label
            best_score = score
    if best_score < 0.74:
        return "", 0.0
    return best_label, best_score


def contains_amount(text: str) -> bool:
    return bool(AMOUNT_RE.search(text or ""))


def extract_typed_value(text: str, value_type: str) -> str:
    text = clean_value(text)
    if not text:
        return ""
    if value_type == "amount":
        matches = AMOUNT_RE.findall(text)
        if not matches:
            return ""
        value = clean_value(matches[-1])
        if re.fullmatch(r"\(?-?\d{1,3}(?:,\d{3})+,\d{2}\)?", value):
            head, tail = value.rsplit(",", 1)
            value = head + "." + tail
        return value
    if value_type == "date":
        match = DATE_RE.search(text)
        return clean_value(match.group(0)) if match else ""
    if value_type == "year":
        match = YEAR_RE.search(text)
        return match.group(0) if match else ""
    if value_type == "alphanumeric":
        for match in ALNUM_ID_RE.finditer(text):
            value = clean_value(match.group(0))
            if DATE_RE.fullmatch(value) or YEAR_RE.fullmatch(value):
                continue
            return value
        return ""
    return text


def is_label_only(line: str, matched_label: str) -> bool:
    remainder = line_without_label(line, matched_label)
    if remainder:
        return False
    return line.strip().endswith(":") or normalize_label(line) == normalize_label(matched_label)


def is_likely_label_value_noise(value: str) -> bool:
    normalized = normalize_label(value)
    if not normalized:
        return True
    if normalized in BAD_VALUE_WORDS:
        return True
    if value.endswith(":"):
        return True
    return False


def validate_value(value: str, spec: FieldSpec) -> bool:
    value = clean_value(value)
    if not value or is_likely_label_value_noise(value):
        return False
    if spec.validator:
        return spec.validator(value)
    if spec.value_type == "amount":
        return isinstance(normalize_amount(value), (int, float))
    if spec.value_type == "date":
        try:
            date_parser.parse(value, fuzzy=False)
            return True
        except Exception:
            return False
    if spec.value_type == "year":
        return bool(re.fullmatch(r"(19|20)\d{2}", value))
    if spec.value_type == "alphanumeric":
        return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_/]{3,}", value))
    return len(value) >= 2 and not looks_like_business_label(value)


def score_candidate(
    spec: FieldSpec,
    value: str,
    label_score: float,
    label_line: DocumentLine,
    value_line: DocumentLine,
    extraction_method: str,
) -> tuple[float, List[str]]:
    reasons: List[str] = []
    distance = abs(value_line.index - label_line.index)
    score = 0.0
    score += min(label_score, 1.0) * 0.34
    reasons.append(f"label_match={label_score:.2f}")

    distance_score = max(0.0, 1.0 - (distance * 0.18))
    score += distance_score * 0.22
    reasons.append(f"distance={distance}")

    if validate_value(value, spec):
        score += 0.28
        reasons.append("field_validation=passed")
    else:
        score -= 0.24
        reasons.append("field_validation=failed")

    if value_line.section in spec.forbidden_sections or label_line.section in spec.forbidden_sections:
        score -= 0.32
        reasons.append(f"forbidden_section={value_line.section}")
    elif value_line.section in spec.preferred_sections or label_line.section in spec.preferred_sections:
        score += 0.08
        reasons.append(f"preferred_section={value_line.section}")

    if extraction_method == "inline":
        score += 0.08
        reasons.append("inline_value")
    elif extraction_method == "next_line":
        score += 0.05
        reasons.append("next_line_value")
    elif extraction_method == "previous_line":
        score += 0.03
        reasons.append("previous_line_value")
        if spec.prefer_previous_line:
            score += 0.08
            reasons.append("field_prefers_previous_line")
    elif extraction_method == "fallback_regex":
        score -= 0.08
        reasons.append("fallback")
    elif extraction_method == "table_row":
        score += 0.1
        reasons.append("table_row_layout")
    elif extraction_method == "label_group":
        score += 0.12
        reasons.append("grouped_label_value_layout")

    if spec.value_type == "alphanumeric" and re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
        score += 0.08
        reasons.append("alphanumeric_shape")
    if spec.value_type == "amount" and contains_amount(value):
        score += 0.06
        reasons.append("amount_shape")
    if spec.value_type == "date":
        try:
            date_parser.parse(value, fuzzy=False)
            score += 0.06
            reasons.append("date_shape")
        except Exception:
            pass

    return max(0.0, min(score, 1.0)), reasons


def build_candidate(
    spec: FieldSpec,
    raw_value: str,
    label_score: float,
    label_line: DocumentLine,
    value_line: DocumentLine,
    extraction_method: str,
) -> ExtractionCandidate | None:
    value = extract_typed_value(raw_value, spec.value_type)
    if not value:
        return None
    score, reasons = score_candidate(spec, value, label_score, label_line, value_line, extraction_method)
    if score < 0.32:
        return None
    source_line = label_line.text if label_line.index == value_line.index else f"{label_line.text} | {value_line.text}"
    return ExtractionCandidate(
        field_name=spec.field_name,
        value=clean_value(value),
        confidence=score,
        source_line=source_line,
        label_line=label_line.text,
        value_line=value_line.text,
        label_index=label_line.index,
        value_index=value_line.index,
        extraction_method=extraction_method,
        score=score,
        reasons=reasons,
    )


def scan_candidates_for_field(lines: List[DocumentLine], spec: FieldSpec) -> List[ExtractionCandidate]:
    candidates: List[ExtractionCandidate] = []
    for line in lines:
        matched_label, label_score = best_label_match(line.text, spec)
        if not matched_label:
            continue

        inline_value = line_without_label(line.text, matched_label)
        if inline_value:
            candidate = build_candidate(spec, inline_value, label_score, line, line, "inline")
            if candidate:
                candidates.append(candidate)

        if spec.allow_previous_line and line.index > 0:
            previous_line = lines[line.index - 1]
            candidate = build_candidate(spec, previous_line.text, label_score, line, previous_line, "previous_line")
            if candidate:
                candidates.append(candidate)

        has_label_candidate = any(item.label_index == line.index for item in candidates)
        if is_label_only(line.text, matched_label) or not inline_value or not has_label_candidate:
            for offset in range(1, spec.max_lookahead + 1):
                next_index = line.index + offset
                if next_index >= len(lines):
                    break
                next_line = lines[next_index]
                if looks_like_business_label(next_line.text) and not validate_value(next_line.text, spec):
                    break
                candidate = build_candidate(spec, next_line.text, label_score, line, next_line, "next_line")
                if candidate:
                    candidates.append(candidate)

    candidates.extend(scan_fallback_candidates(lines, spec))
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def scan_label_group_candidates(lines: List[DocumentLine], specs: List[FieldSpec]) -> Dict[str, List[ExtractionCandidate]]:
    grouped: Dict[str, List[ExtractionCandidate]] = {spec.field_name: [] for spec in specs}
    for start_index in range(len(lines)):
        label_items: List[Dict[str, Any]] = []
        cursor = start_index
        while cursor < len(lines) and len(label_items) < 6:
            line = lines[cursor]
            matches: List[Dict[str, Any]] = []
            for spec in specs:
                matched_label, label_score = best_label_match(line.text, spec)
                if matched_label and is_label_only(line.text, matched_label):
                    matches.append(
                        {
                            "line": line,
                            "spec": spec,
                            "matched_label": matched_label,
                            "label_score": label_score,
                        }
                    )
            if not matches:
                break
            matches.sort(key=lambda item: item["label_score"], reverse=True)
            if len(matches) > 1 and matches[0]["label_score"] < 0.92:
                break
            label_items.append(matches[0])
            cursor += 1

        if len(label_items) < 2:
            continue

        value_lines: List[DocumentLine] = []
        value_cursor = cursor
        while value_cursor < len(lines) and len(value_lines) < len(label_items):
            value_line = lines[value_cursor]
            if looks_like_business_label(value_line.text):
                break
            value_lines.append(value_line)
            value_cursor += 1

        if len(value_lines) < len(label_items):
            continue

        for label_item, value_line in zip(label_items, value_lines):
            spec = label_item["spec"]
            candidate = build_candidate(
                spec,
                value_line.text,
                label_item["label_score"],
                label_item["line"],
                value_line,
                "label_group",
            )
            if candidate:
                grouped[spec.field_name].append(candidate)
    return grouped


def _all_label_occurrences(line: str, specs: List[FieldSpec]) -> List[Dict[str, Any]]:
    occurrences: List[Dict[str, Any]] = []
    lowered = line.lower()
    for spec in specs:
        best: Dict[str, Any] | None = None
        for label in sorted(spec.labels, key=len, reverse=True):
            label_pattern = re.escape(label.lower()).replace(r"\ ", r"\s+")
            match = re.search(
                rf"(?<![a-z0-9]){label_pattern}(?![a-z0-9])",
                lowered,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            label_score = label_similarity(line[match.start() : match.end()], label)
            if label_score < 0.74:
                continue
            candidate = {
                "field_name": spec.field_name,
                "spec": spec,
                "label": label,
                "start": match.start(),
                "end": match.end(),
                "label_score": label_score,
            }
            if best is None or len(label) > len(best["label"]):
                best = candidate
        if best:
            occurrences.append(best)
    occurrences.sort(key=lambda item: item["start"])
    compact: List[Dict[str, Any]] = []
    used_fields = set()
    for item in occurrences:
        if item["field_name"] in used_fields:
            continue
        compact.append(item)
        used_fields.add(item["field_name"])
    return compact


def split_table_cells(line: str) -> List[str]:
    cells = [cell.strip(" :|") for cell in re.split(r"\t+|\s{2,}|\s+\|\s+|\|", line) if cell.strip(" :|")]
    return cells if len(cells) > 1 else []


def _typed_values_in_order(line: str, value_type: str) -> List[str]:
    if value_type == "amount":
        return [clean_value(value) for value in AMOUNT_RE.findall(line)]
    if value_type == "date":
        return [clean_value(match.group(0)) for match in DATE_RE.finditer(line)]
    if value_type == "year":
        return [match.group(0) for match in YEAR_RE.finditer(line)]
    if value_type == "alphanumeric":
        values = []
        for match in ALNUM_ID_RE.finditer(line):
            value = clean_value(match.group(0))
            if not DATE_RE.search(value) and not YEAR_RE.fullmatch(value):
                values.append(value)
        return values
    cells = split_table_cells(line)
    return cells if cells else [line.strip()]


def scan_table_layout_candidates(lines: List[DocumentLine], specs: List[FieldSpec]) -> Dict[str, List[ExtractionCandidate]]:
    table_candidates: Dict[str, List[ExtractionCandidate]] = {spec.field_name: [] for spec in specs}
    for label_line in lines:
        occurrences = _all_label_occurrences(label_line.text, specs)
        if len(occurrences) < 2:
            continue
        for offset in range(1, 3):
            value_index = label_line.index + offset
            if value_index >= len(lines):
                break
            value_line = lines[value_index]
            if looks_like_business_label(value_line.text):
                continue
            cells = split_table_cells(value_line.text)
            type_positions: Dict[str, int] = {}
            for occurrence_index, occurrence in enumerate(occurrences):
                spec: FieldSpec = occurrence["spec"]
                raw_value = ""
                if cells and occurrence_index < len(cells):
                    raw_value = cells[occurrence_index]
                else:
                    type_values = _typed_values_in_order(value_line.text, spec.value_type)
                    position = type_positions.get(spec.value_type, 0)
                    if position < len(type_values):
                        raw_value = type_values[position]
                        type_positions[spec.value_type] = position + 1
                if not raw_value:
                    continue
                candidate = build_candidate(
                    spec,
                    raw_value,
                    occurrence["label_score"],
                    label_line,
                    value_line,
                    "table_row",
                )
                if candidate:
                    table_candidates[spec.field_name].append(candidate)
    return table_candidates


def scan_fallback_candidates(lines: List[DocumentLine], spec: FieldSpec) -> List[ExtractionCandidate]:
    candidates: List[ExtractionCandidate] = []
    if not spec.fallback_patterns:
        return candidates
    full_text = "\n".join(line.text for line in lines)
    for pattern in spec.fallback_patterns:
        for match in re.finditer(pattern, full_text, flags=re.IGNORECASE | re.MULTILINE):
            raw_value = match.group(1) if match.groups() else match.group(0)
            label_text = match.group(0).split(str(raw_value), 1)[0].strip() or spec.labels[0]
            source_text = match.group(0).strip()
            source_index = find_line_index_for_text(lines, source_text)
            source_line = lines[source_index] if source_index is not None else DocumentLine(0, source_text)
            label_line = DocumentLine(source_line.index, label_text, source_line.section)
            candidate = build_candidate(spec, raw_value, 0.78, label_line, source_line, "fallback_regex")
            if candidate:
                candidates.append(candidate)
    return candidates


def find_line_index_for_text(lines: List[DocumentLine], text: str) -> int | None:
    needle = normalize_label(text)
    for line in lines:
        if normalize_label(line.text) in needle or needle in normalize_label(line.text):
            return line.index
    return None


def extract_with_specs(text: str, specs: Iterable[FieldSpec]) -> Dict[str, Any]:
    lines = split_document_lines(text)
    specs = list(specs)
    table_candidates = scan_table_layout_candidates(lines, specs)
    label_group_candidates = scan_label_group_candidates(lines, specs)
    fields: Dict[str, str] = {}
    metadata: Dict[str, Dict[str, Any]] = {}
    all_candidates: Dict[str, List[Dict[str, Any]]] = {}

    for spec in specs:
        candidates = scan_candidates_for_field(lines, spec)
        candidates.extend(table_candidates.get(spec.field_name, []))
        candidates.extend(label_group_candidates.get(spec.field_name, []))
        candidates.sort(key=lambda item: item.score, reverse=True)
        all_candidates[spec.field_name] = [candidate.to_metadata() for candidate in candidates[:5]]
        if candidates:
            winner = candidates[0]
            fields[spec.field_name] = winner.value
            metadata[spec.field_name] = winner.to_metadata()
        else:
            fields[spec.field_name] = ""
            metadata[spec.field_name] = {
                "field_name": spec.field_name,
                "value": "",
                "confidence": 0.0,
                "source_line": "",
                "label_line": "",
                "value_line": "",
                "label_index": None,
                "value_index": None,
                "extraction_method": "not_found",
                "score": 0.0,
                "reasons": ["no_candidate_found"],
            }

    return {
        "fields": fields,
        "metadata": metadata,
        "candidates": all_candidates,
        "lines": [asdict(line) for line in lines],
    }
