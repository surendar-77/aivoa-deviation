"""Document reading: txt, eml, pdf (text layer) and jpg (OCR, skipped if Tesseract absent)."""
from pathlib import Path

import pytest

from app.reader import DocumentReadError, read_document, tesseract_available

SAMPLES = Path(__file__).resolve().parent / "fixtures"
needs_tesseract = pytest.mark.skipif(not tesseract_available(), reason="Tesseract not installed")


def _read(name):
    return read_document(name, (SAMPLES / name).read_bytes())


def test_txt():
    text, method = _read("deviation_email.txt")
    assert method == "plain text"
    assert "R-201" in text and "60-65 °C" in text


def test_eml_headers_and_body():
    text, method = _read("deviation_email.eml")
    assert method.startswith("email")
    assert "Subject: Temperature excursion" in text and "From: Ravi Kumar" in text
    assert "71 °C" in text


def test_pdf_text_layer():
    text, method = _read("deviation_report.pdf")
    assert method == "PDF text layer (pypdf)"
    assert "AC-2609-042" in text and "NMT 0.5% w/w" in text


@needs_tesseract
def test_jpg_ocr():
    text, method = _read("deviation_scan.jpg")
    assert method == "image OCR (Tesseract)"
    assert "LP-2609-009" in text
    assert "CF-102" in text


def test_unsupported_and_empty_files():
    with pytest.raises(DocumentReadError, match="Unsupported"):
        read_document("report.docx", b"abc")
    with pytest.raises(DocumentReadError, match="empty"):
        read_document("a.txt", b"")
