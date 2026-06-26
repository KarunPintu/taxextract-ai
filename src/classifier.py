import re
from functools import lru_cache
from typing import Any, Dict, List, Tuple

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
except Exception:  # pragma: no cover - app falls back to rules when sklearn is unavailable
    TfidfVectorizer = None
    LogisticRegression = None
    Pipeline = None


CLASSIFIER_KEYWORDS = {
    "Invoice": {
        "invoice": 8,
        "invoice number": 12,
        "invoice no": 10,
        "vendor": 6,
        "supplier": 6,
        "subtotal": 8,
        "bill to": 8,
        "customer": 5,
        "total amount": 8,
        "due date": 4,
        "tax amount": 4,
    },
    "Assessment": {
        "assessment": 10,
        "assessment year": 12,
        "assessed value": 10,
        "assessment value": 10,
        "taxable value": 8,
        "total taxable": 8,
        "market value": 8,
        "market information": 9,
        "parcel": 8,
        "parcel id": 10,
        "exempt value": 5,
        "business type": 4,
        "economic life": 4,
        "appeal deadline": 10,
        "notice date": 4,
    },
    "Tax Bill": {
        "tax bill": 14,
        "tax year": 10,
        "real estate taxes": 10,
        "total due": 10,
        "total tax due": 10,
        "installment": 10,
        "penalty": 7,
        "interest": 7,
        "tax amount": 8,
        "parcel": 6,
        "pin": 5,
        "amount due": 6,
        "state equalized value": 7,
        "net taxable value": 7,
        "county collector": 6,
    },
}


DEFAULT_TRAINING_EXAMPLES = [
    ("Invoice", "Invoice number vendor supplier bill to subtotal tax amount invoice total due date line items"),
    ("Invoice", "Invoice Date Customer Number Reference Billing Period VAT Charged Subtotal Total Amount EUR"),
    ("Invoice", "Bill To Sold To Invoice No Inv No payment due sales tax subtotal total"),
    ("Invoice", "Supplier invoice remittance invoice date client name services rendered total amount"),
    ("Assessment", "Assessment notice assessment year parcel id owner name assessed value taxable value market value appeal deadline"),
    ("Assessment", "Property assessment owner address county acreage total assessed value fair market value exemption value"),
    ("Assessment", "Assessment Year APN PIN taxable value notice date appeal due date property owner"),
    ("Assessment", "Real estate assessment parcel number market value exemption assessed value taxable value"),
    ("Assessment", "Personal property record summary parcel owner mailing address business type economic life market information market value assessment value exempt value total taxable"),
    ("Tax Bill", "Tax bill tax year total due installment penalty interest parcel id tax amount assessed value taxable value"),
    ("Tax Bill", "Property tax statement tax bill number amount due net tax installment due date jurisdiction"),
    ("Tax Bill", "Tax Year Parcel Number First Installment Second Installment Total Amount Due Penalty Interest"),
    ("Tax Bill", "County tax bill current tax total due installment 1 due date installment 2 due date"),
    ("Tax Bill", "Real Estate Taxes payable county collector PIN state equalized value net taxable value total tax due first installment second installment"),
]


def _find_keyword_matches(text: str, keyword_weights: Dict[str, int]) -> Tuple[int, List[str]]:
    score = 0
    matches: List[str] = []
    for keyword, weight in keyword_weights.items():
        pattern = r"\b" + re.escape(keyword).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            score += weight
            matches.append(keyword)
    return score, matches


def _rule_classify(text: str, file_name: str = "") -> Dict[str, object]:
    combined_text = f"{file_name}\n{text or ''}".lower()
    raw_scores: Dict[str, int] = {}
    matches_by_class: Dict[str, List[str]] = {}

    for document_class, keyword_weights in CLASSIFIER_KEYWORDS.items():
        score, matches = _find_keyword_matches(combined_text, keyword_weights)
        raw_scores[document_class] = score
        matches_by_class[document_class] = matches

    best_class = max(raw_scores, key=raw_scores.get)
    best_score = raw_scores[best_class]
    if best_score == 0:
        return {
            "document_class": "Unknown",
            "confidence": 0,
            "matching_keywords": [],
            "explanation": "No strong document class keywords were detected.",
            "scores": raw_scores,
        }

    max_possible = sum(CLASSIFIER_KEYWORDS[best_class].values())
    next_best = max([score for cls, score in raw_scores.items() if cls != best_class] or [0])
    coverage = best_score / max_possible
    dominance = (best_score - next_best) / max(best_score, 1)
    confidence = int(min(98, max(35, 45 + (coverage * 38) + (dominance * 28))))

    return {
        "document_class": best_class,
        "confidence": confidence,
        "matching_keywords": matches_by_class[best_class],
        "explanation": (
            f"Matched {len(matches_by_class[best_class])} weighted keyword(s) "
            f"for {best_class}."
        ),
        "scores": raw_scores,
    }


def _training_signature(user_training_examples: List[Dict[str, Any]] | None = None) -> Tuple[Tuple[str, str], ...]:
    examples = [(label, text) for label, text in DEFAULT_TRAINING_EXAMPLES]
    for example in user_training_examples or []:
        label = str(example.get("label", "")).strip()
        sample_text = str(example.get("text", "")).strip()
        if label in CLASSIFIER_KEYWORDS and sample_text:
            examples.append((label, sample_text[:10000]))
    return tuple(examples)


@lru_cache(maxsize=16)
def _build_ml_model(training_signature: Tuple[Tuple[str, str], ...]):
    if Pipeline is None or TfidfVectorizer is None or LogisticRegression is None:
        return None
    labels = [label for label, _ in training_signature]
    samples = [text for _, text in training_signature]
    if len(set(labels)) < 2:
        return None
    model = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    min_df=1,
                    max_features=6000,
                    strip_accents="unicode",
                ),
            ),
            ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    model.fit(samples, labels)
    return model


def _ml_classify(text: str, file_name: str = "", user_training_examples: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    model = _build_ml_model(_training_signature(user_training_examples))
    if model is None:
        return {
            "available": False,
            "document_class": "Unknown",
            "confidence": 0,
            "probabilities": {},
            "explanation": "Local ML classifier is unavailable. Rules were used instead.",
        }
    sample = f"{file_name}\n{text or ''}"
    probabilities = model.predict_proba([sample])[0]
    classes = [str(cls) for cls in model.named_steps["classifier"].classes_]
    probability_map = {
        cls: round(float(prob) * 100, 2)
        for cls, prob in zip(classes, probabilities)
    }
    best_class = max(probability_map, key=probability_map.get)
    return {
        "available": True,
        "document_class": best_class,
        "confidence": int(probability_map[best_class]),
        "probabilities": probability_map,
        "training_examples": len(_training_signature(user_training_examples)),
        "user_training_examples": len(user_training_examples or []),
        "explanation": (
            "TF-IDF + Logistic Regression predicted "
            f"{best_class} with {probability_map[best_class]}% probability."
        ),
    }


def classify_document(
    text: str,
    file_name: str = "",
    user_training_examples: List[Dict[str, Any]] | None = None,
) -> Dict[str, object]:
    rule_result = _rule_classify(text, file_name=file_name)
    ml_result = _ml_classify(text, file_name=file_name, user_training_examples=user_training_examples)

    if not ml_result.get("available"):
        rule_result["classifier_type"] = "Rules only"
        rule_result["rule_result"] = rule_result.copy()
        rule_result["ml_result"] = ml_result
        return rule_result

    class_scores: Dict[str, float] = {}
    user_examples = len(user_training_examples or [])
    ml_weight = 0.55 if user_examples else 0.45
    rule_weight = 1.0 - ml_weight
    for document_class in CLASSIFIER_KEYWORDS:
        rule_component = float(rule_result.get("confidence", 0)) if rule_result.get("document_class") == document_class else 0.0
        ml_component = float(ml_result.get("probabilities", {}).get(document_class, 0))
        class_scores[document_class] = (rule_component * rule_weight) + (ml_component * ml_weight)

    best_class = max(class_scores, key=class_scores.get)
    confidence = int(min(99, max(class_scores[best_class], rule_result.get("confidence", 0) if best_class == rule_result.get("document_class") else 0)))

    agreement = rule_result.get("document_class") == ml_result.get("document_class")
    explanation = (
        f"Hybrid classifier combined rules ({rule_result.get('document_class')} "
        f"{rule_result.get('confidence')}%) and local ML ({ml_result.get('document_class')} "
        f"{ml_result.get('confidence')}%)."
    )
    if agreement:
        confidence = min(99, confidence + 8)
        explanation += " Both layers agreed, so confidence was boosted."
    elif user_examples:
        explanation += " User training feedback was included in the ML layer."

    return {
        "document_class": best_class,
        "confidence": confidence,
        "matching_keywords": rule_result.get("matching_keywords", []),
        "explanation": explanation,
        "scores": class_scores,
        "classifier_type": "Hybrid Rules + Local ML",
        "rule_result": rule_result,
        "ml_result": ml_result,
        "hybrid_weights": {"rules": rule_weight, "ml": ml_weight},
    }
