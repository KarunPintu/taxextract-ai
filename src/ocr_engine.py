from typing import Dict, Iterable, List

from PIL import Image

try:
    import pytesseract
    from pytesseract import Output, TesseractNotFoundError
except Exception:  # pragma: no cover - handled at runtime in the app
    pytesseract = None
    Output = None

    class TesseractNotFoundError(Exception):
        pass


OCR_UNAVAILABLE_MESSAGE = (
    "OCR engine is not available in this environment. "
    "This document has been routed to human review."
)


def is_ocr_available() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _empty_result(error: str = "") -> Dict[str, object]:
    return {
        "text": "",
        "confidence": None,
        "available": False,
        "error": error,
        "message": OCR_UNAVAILABLE_MESSAGE,
    }


def ocr_image(image: Image.Image) -> Dict[str, object]:
    if not is_ocr_available():
        return _empty_result()

    try:
        data = pytesseract.image_to_data(image, output_type=Output.DICT)
        words: List[str] = []
        confidences: List[float] = []
        for text, confidence in zip(data.get("text", []), data.get("conf", [])):
            text = (text or "").strip()
            if not text:
                continue
            try:
                confidence_value = float(confidence)
            except (TypeError, ValueError):
                confidence_value = -1
            if confidence_value >= 0:
                confidences.append(confidence_value)
            words.append(text)
        average_confidence = round(sum(confidences) / len(confidences), 1) if confidences else None
        return {
            "text": " ".join(words),
            "confidence": average_confidence,
            "available": True,
            "error": "",
            "message": "OCR completed locally with Tesseract.",
        }
    except TesseractNotFoundError:
        return _empty_result()
    except Exception as exc:
        try:
            text = pytesseract.image_to_string(image)
            return {
                "text": text,
                "confidence": None,
                "available": True,
                "error": f"OCR confidence details unavailable: {exc}",
                "message": "OCR text extraction completed without confidence details.",
            }
        except Exception as fallback_exc:
            return _empty_result(str(fallback_exc))


def ocr_images(images: Iterable[Image.Image]) -> Dict[str, object]:
    texts: List[str] = []
    confidences: List[float] = []
    available = is_ocr_available()
    errors: List[str] = []

    if not available:
        return _empty_result()

    for image in images:
        result = ocr_image(image)
        if result.get("text"):
            texts.append(str(result["text"]))
        if result.get("confidence") is not None:
            confidences.append(float(result["confidence"]))
        if result.get("error"):
            errors.append(str(result["error"]))

    return {
        "text": "\n".join(texts).strip(),
        "confidence": round(sum(confidences) / len(confidences), 1) if confidences else None,
        "available": available,
        "error": "; ".join(errors),
        "message": "OCR completed locally with Tesseract.",
    }
