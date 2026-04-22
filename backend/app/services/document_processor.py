import io
import re
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── PDF extraction ────────────────────────────────────────────────────────────

def _extract_pdf(data: bytes) -> str:
    import pdfplumber
    text_parts = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                text_parts.append(text)
            else:
                logger.debug("Page %d has no text layer — trying OCR", i + 1)
                text_parts.append(_ocr_page(page))
    return "\n\n".join(text_parts)


def _ocr_page(page) -> str:
    """Fallback OCR using pytesseract for scanned pages."""
    try:
        import pytesseract
        from PIL import Image
        img = page.to_image(resolution=200).original
        return pytesseract.image_to_string(img, lang="deu+eng")
    except Exception as exc:
        logger.warning("OCR failed for page: %s", exc)
        return ""


# ── DOCX extraction ───────────────────────────────────────────────────────────

def _extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


# ── Text cleaning ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Remove non-printable characters
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\x80-\xFF]", "", text)
    return text.strip()


# ── Public interface ──────────────────────────────────────────────────────────

def extract_text(file_data: bytes, content_type: str) -> str:
    """
    Extract and clean text from a PDF or DOCX file.
    Returns cleaned plain text ready for the AI service.
    Raises ValueError if extraction yields no usable text.
    """
    logger.info("Extracting text", extra={"content_type": content_type, "bytes": len(file_data)})

    if content_type == "application/pdf":
        raw = _extract_pdf(file_data)
    elif content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        raw = _extract_docx(file_data)
    else:
        raise ValueError(f"Unsupported content type: {content_type}")

    cleaned = _clean_text(raw)

    if len(cleaned) < 50:
        raise ValueError(
            "Could not extract meaningful text from the document. "
            "The file may be a scanned image without OCR support, password-protected, or corrupt."
        )

    logger.info("Extracted %d characters", len(cleaned))
    return cleaned


def chunk_text(text: str, max_chars: int = 12000) -> list[str]:
    """
    Split long documents into chunks that fit within the model's context window.
    Splits on paragraph boundaries where possible.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current += para + "\n\n"
        else:
            if current:
                chunks.append(current.strip())
            # If a single paragraph is too long, hard-split it
            if len(para) > max_chars:
                for i in range(0, len(para), max_chars):
                    chunks.append(para[i:i + max_chars])
            else:
                current = para + "\n\n"

    if current.strip():
        chunks.append(current.strip())

    logger.info("Split document into %d chunks", len(chunks))
    return chunks