"""Turn an uploaded file into plain text for the AI (the graph's read_input step).

Supported: .txt, .eml, .pdf (text layer -> OCR fallback for scans), .jpg/.jpeg/.png (Tesseract).
Each reader returns (text, method) so the UI can show HOW the text was obtained
- important for trust: users should know when text came from OCR (may contain errors).
"""
from __future__ import annotations

import io
import os
import re
import shutil
from email import policy
from email.parser import BytesParser
from html import unescape
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from .config import settings

SUPPORTED_EXTENSIONS = {".txt", ".eml", ".pdf", ".jpg", ".jpeg", ".png"}
MIN_PDF_TEXT_CHARS = 40  # below this, the PDF is treated as a scan and OCR'd


class DocumentReadError(Exception):
    """User-facing error while reading an uploaded document."""


# ---------------------------------------------------------------------------
# Tesseract setup
# ---------------------------------------------------------------------------
_WINDOWS_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def _tesseract():
    """Import pytesseract and point it at the binary (from .env, PATH or common Windows paths)."""
    import pytesseract

    candidates = [settings.TESSERACT_CMD] if settings.TESSERACT_CMD else []
    candidates += [shutil.which("tesseract") or ""] + _WINDOWS_TESSERACT_PATHS
    for path in candidates:
        if path and Path(path).exists():
            pytesseract.pytesseract.tesseract_cmd = path
            return pytesseract
    raise DocumentReadError(
        "Tesseract OCR is not installed or not found. Install it and set TESSERACT_CMD in backend/.env."
    )


def tesseract_available() -> bool:
    try:
        _tesseract()
        return True
    except DocumentReadError:
        return False


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """Grayscale -> upscale small images -> autocontrast -> light sharpen.

    Why: Tesseract is most accurate on high-contrast text ~30px tall; phone photos
    and low-res scans are often small and washed out.
    """
    img = ImageOps.exif_transpose(img)  # respect phone camera rotation
    img = img.convert("L")
    if img.width < 1800:
        scale = 1800 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=2)
    return img.filter(ImageFilter.SHARPEN)


def ocr_image(img: Image.Image) -> str:
    pytesseract = _tesseract()
    return pytesseract.image_to_string(preprocess_for_ocr(img), config="--oem 3 --psm 6")


# ---------------------------------------------------------------------------
# Per-format readers
# ---------------------------------------------------------------------------
def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", html)
    return unescape(re.sub(r"<[^>]+>", "", html))


def read_eml(data: bytes) -> str:
    """Email -> 'Subject/From/Date/To' header block + plain-text body."""
    msg = BytesParser(policy=policy.default).parsebytes(data)
    headers = [f"{h}: {msg[h]}" for h in ("Subject", "From", "To", "Date") if msg[h]]
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if body_part is not None:
        body = body_part.get_content()
        if body_part.get_content_type() == "text/html":
            body = _html_to_text(body)
    return "\n".join(headers) + "\n\n" + body.strip()


def read_pdf(data: bytes) -> tuple[str, str]:
    """Use the PDF text layer; if (almost) empty it is a scan -> OCR each page."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # corrupt / encrypted PDF
        raise DocumentReadError(f"Could not open PDF: {exc}") from exc
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if len(text) >= MIN_PDF_TEXT_CHARS:
        return text, "PDF text layer (pypdf)"

    # Scanned PDF. Preferred: render pages with poppler (pdf2image).
    try:
        from pdf2image import convert_from_bytes

        pages = convert_from_bytes(data, dpi=300, poppler_path=settings.POPPLER_PATH or None)
        return "\n".join(ocr_image(p) for p in pages).strip(), "scanned PDF OCR (poppler + Tesseract)"
    except DocumentReadError:
        raise
    except Exception:
        pass  # poppler not installed -> fall back to embedded page images

    # Fallback without poppler: a scanned PDF is usually one embedded image per page.
    images = [Image.open(io.BytesIO(img.data)) for page in reader.pages for img in page.images]
    if not images:
        raise DocumentReadError("PDF has no text layer and no images to OCR.")
    return "\n".join(ocr_image(im) for im in images).strip(), "scanned PDF OCR (embedded images + Tesseract)"


def read_image(data: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise DocumentReadError(f"Could not open image: {exc}") from exc
    return ocr_image(img).strip()


def read_document(filename: str, data: bytes) -> tuple[str, str]:
    """Dispatch on file extension. Returns (text, extraction_method)."""
    ext = Path(filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentReadError(
            f"Unsupported file type '{ext or '?'}'. Upload PDF, JPG/JPEG, PNG, TXT or EML."
        )
    if not data:
        raise DocumentReadError("The uploaded file is empty.")
    if ext == ".txt":
        text, method = _decode(data), "plain text"
    elif ext == ".eml":
        text, method = read_eml(data), "email (.eml) parser"
    elif ext == ".pdf":
        text, method = read_pdf(data)
    else:
        text, method = read_image(data), "image OCR (Tesseract)"
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    if not text:
        raise DocumentReadError("No readable text was found in the document.")
    return text, method
