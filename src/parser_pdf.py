from io import BytesIO
from typing import Dict, List

from PIL import Image

try:
    import fitz
except Exception:  # pragma: no cover - handled at runtime in the app
    fitz = None

from src.utils import clean_text


MIN_DIRECT_TEXT_CHARS = 80


def extract_pdf_text(file_bytes: bytes) -> Dict[str, object]:
    result = {
        "text": "",
        "pages": 0,
        "requires_ocr": False,
        "error": "",
        "parser": "PyMuPDF",
    }
    if fitz is None:
        result["error"] = "PyMuPDF is not available."
        result["requires_ocr"] = True
        return result

    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as document:
            result["pages"] = len(document)
            text_parts = []
            for page in document:
                blocks = page.get_text("blocks")
                for block in blocks:
                    block_text = str(block[4]).strip()
                    if block_text:
                        text_parts.append(block_text)
        text = clean_text("\n\n".join(text_parts))
        result["text"] = text
        result["requires_ocr"] = len(text) < MIN_DIRECT_TEXT_CHARS
    except Exception as exc:
        result["error"] = f"PDF parsing failed: {exc}"
        result["requires_ocr"] = True
    return result


def render_pdf_pages_to_images(
    file_bytes: bytes,
    max_pages: int = 5,
    zoom: float = 2.0,
) -> List[Image.Image]:
    images: List[Image.Image] = []
    if fitz is None:
        return images

    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as document:
            matrix = fitz.Matrix(zoom, zoom)
            for page in document[:max_pages]:
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
                images.append(image.copy())
    except Exception:
        return images
    return images
