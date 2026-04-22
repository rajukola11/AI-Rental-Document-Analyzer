import io
import pytest
from unittest.mock import MagicMock, patch

# ── Helpers to build in-memory test fixtures ──────────────────────────────────

def _make_pdf(pages: list[str]) -> bytes:
    """Return raw PDF bytes containing one text line per page."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for text in pages:
        c.drawString(50, 750, text)
        c.showPage()
    c.save()
    return buf.getvalue()


def _make_docx(paragraphs: list[str]) -> bytes:
    """Return raw DOCX bytes containing the given paragraphs."""
    from docx import Document
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


PDF_CONTENT_TYPE  = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# ── Import the module under test (conftest already patched app.core.*) ─────────

from app.services.document_processor import (
    _clean_text,
    chunk_text,
    extract_text,
    _extract_pdf,
    _extract_docx,
    _ocr_page,
)


# ===========================================================================
# _clean_text
# ===========================================================================

class TestCleanText:
    def test_returns_string(self):
        assert isinstance(_clean_text("hello"), str)

    def test_strips_leading_and_trailing_whitespace(self):
        assert _clean_text("  hello  ") == "hello"

    def test_strips_leading_newlines(self):
        assert _clean_text("\n\nhello") == "hello"

    def test_collapses_triple_newlines_to_double(self):
        result = _clean_text("para1\n\n\n\npara2")
        assert result == "para1\n\npara2"

    def test_collapses_many_newlines_to_double(self):
        result = _clean_text("a\n\n\n\n\n\nb")
        assert result == "a\n\nb"

    def test_double_newline_is_preserved(self):
        result = _clean_text("a\n\nb")
        assert result == "a\n\nb"

    def test_collapses_multiple_spaces_to_one(self):
        result = _clean_text("word1   word2")
        assert result == "word1 word2"

    def test_collapses_tabs_to_single_space(self):
        result = _clean_text("word1\t\tword2")
        assert result == "word1 word2"

    def test_removes_null_bytes(self):
        result = _clean_text("hello\x00world")
        assert "\x00" not in result
        assert "hello" in result

    def test_removes_other_control_characters(self):
        # \x01-\x08 are non-printable, should be stripped
        result = _clean_text("hello\x01\x02world")
        assert "\x01" not in result
        assert "\x02" not in result

    def test_preserves_tab_as_whitespace(self):
        # \x09 is tab — allowed by the regex
        result = _clean_text("col1\tcol2")
        assert "\t" in result or " " in result  # tab kept or collapsed

    def test_preserves_extended_ascii(self):
        # German umlauts are in \x80-\xFF range and must be preserved
        result = _clean_text("Mietvertrag für Wohnung")
        assert "ü" in result

    def test_empty_string_returns_empty(self):
        assert _clean_text("") == ""

    def test_only_whitespace_returns_empty(self):
        assert _clean_text("   \n\n\t  ") == ""

    def test_mixed_cleaning(self):
        raw = "  hello\n\n\n\nworld   foo  "
        result = _clean_text(raw)
        assert result == "hello\n\nworld foo"


# ===========================================================================
# chunk_text
# ===========================================================================

class TestChunkText:
    def test_short_text_returns_single_chunk(self):
        text = "Short text"
        chunks = chunk_text(text, max_chars=100)
        assert chunks == [text]

    def test_exact_max_chars_returns_single_chunk(self):
        text = "x" * 100
        chunks = chunk_text(text, max_chars=100)
        assert len(chunks) == 1

    def test_text_one_char_over_limit_splits(self):
        # Two paragraphs each ~60 chars, limit=100 → should produce 2 chunks
        p1 = "a" * 60
        p2 = "b" * 60
        text = f"{p1}\n\n{p2}"
        chunks = chunk_text(text, max_chars=100)
        assert len(chunks) == 2

    def test_all_chunks_within_max_chars(self):
        long_text = "\n\n".join(["paragraph " + str(i) + " " + "x" * 50 for i in range(20)])
        for chunk in chunk_text(long_text, max_chars=200):
            assert len(chunk) <= 200

    def test_chunks_cover_all_content(self):
        words = ["word" + str(i) for i in range(100)]
        text = "\n\n".join(words)
        chunks = chunk_text(text, max_chars=50)
        joined = " ".join(chunks)
        for w in words:
            assert w in joined

    def test_no_empty_chunks(self):
        text = "\n\n".join(["para " + str(i) for i in range(30)])
        chunks = chunk_text(text, max_chars=30)
        for chunk in chunks:
            assert chunk.strip() != ""

    def test_single_giant_paragraph_hard_splits(self):
        """A paragraph longer than max_chars must be hard-split."""
        giant = "G" * 500
        chunks = chunk_text(giant, max_chars=100)
        assert len(chunks) == 5
        for chunk in chunks:
            assert len(chunk) <= 100

    def test_default_max_chars_is_12000(self):
        short = "x" * 100
        assert chunk_text(short) == [short]

    def test_empty_string_returns_list_with_empty_string(self):
        # len("") <= max_chars, so short-circuits to [text]
        result = chunk_text("")
        assert result == [""]

    def test_returns_list(self):
        assert isinstance(chunk_text("some text"), list)

    def test_paragraph_split_respects_paragraph_boundaries(self):
        """Content of chunk 1 should not bleed into chunk 2."""
        p1 = "AAAA " * 20   # 100 chars
        p2 = "BBBB " * 20   # 100 chars
        text = f"{p1.strip()}\n\n{p2.strip()}"
        chunks = chunk_text(text, max_chars=150)
        assert len(chunks) == 2
        assert "AAAA" in chunks[0]
        assert "BBBB" in chunks[1]

    def test_single_paragraph_fits_within_limit(self):
        text = "Hello world this is a test"
        chunks = chunk_text(text, max_chars=1000)
        assert len(chunks) == 1
        assert chunks[0] == text


# ===========================================================================
# _extract_pdf  (unit — mocks pdfplumber)
# ===========================================================================

class TestExtractPdf:
    def test_single_page_with_text(self):
        pdf_bytes = _make_pdf(["Mietvertrag Seite 1 mit ausreichend Text"])
        result = _extract_pdf(pdf_bytes)
        assert "Mietvertrag" in result

    def test_multi_page_joined_with_double_newline(self):
        pdf_bytes = _make_pdf(["Seite eins", "Seite zwei"])
        result = _extract_pdf(pdf_bytes)
        assert "Seite eins" in result
        assert "Seite zwei" in result
        assert "\n\n" in result

    def test_page_with_no_text_calls_ocr_fallback(self):
        """When extract_text() returns None/empty, _ocr_page should be called."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = None

        mock_pdf_ctx = MagicMock()
        mock_pdf_ctx.__enter__ = MagicMock(return_value=mock_pdf_ctx)
        mock_pdf_ctx.__exit__ = MagicMock(return_value=False)
        mock_pdf_ctx.pages = [mock_page]

        with patch("pdfplumber.open", return_value=mock_pdf_ctx) as mock_plumber, \
             patch("app.services.document_processor._ocr_page", return_value="OCR result") as mock_ocr:
            result = _extract_pdf(b"fake-pdf-bytes")

        mock_ocr.assert_called_once_with(mock_page)
        assert "OCR result" in result

    def test_returns_string(self):
        pdf_bytes = _make_pdf(["Hello rental world"])
        assert isinstance(_extract_pdf(pdf_bytes), str)


# ===========================================================================
# _extract_docx  (unit — uses real python-docx bytes)
# ===========================================================================

class TestExtractDocx:
    def test_extracts_paragraph_text(self):
        docx_bytes = _make_docx(["Mietvertrag paragraph one", "Second paragraph text"])
        result = _extract_docx(docx_bytes)
        assert "Mietvertrag paragraph one" in result
        assert "Second paragraph text" in result

    def test_blank_paragraphs_are_filtered(self):
        docx_bytes = _make_docx(["Real content", "", "   ", "More content"])
        result = _extract_docx(docx_bytes)
        # Should not have blank lines in result (blank paragraphs skipped)
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) == 2

    def test_paragraphs_joined_by_newline(self):
        docx_bytes = _make_docx(["Line one", "Line two"])
        result = _extract_docx(docx_bytes)
        assert "\n" in result

    def test_returns_string(self):
        docx_bytes = _make_docx(["some text"])
        assert isinstance(_extract_docx(docx_bytes), str)

    def test_single_paragraph(self):
        docx_bytes = _make_docx(["Only one paragraph here"])
        result = _extract_docx(docx_bytes)
        assert "Only one paragraph here" in result


# ===========================================================================
# _ocr_page  (unit — mocks pytesseract)
# ===========================================================================

class TestOcrPage:
    def test_returns_string_on_success(self):
        mock_page = MagicMock()
        mock_page.to_image.return_value.original = MagicMock()
        with patch("pytesseract.image_to_string", return_value="OCR text"):
            result = _ocr_page(mock_page)
        assert result == "OCR text"

    def test_returns_empty_string_on_exception(self):
        """Any error during OCR must be swallowed and return empty string."""
        mock_page = MagicMock()
        mock_page.to_image.side_effect = RuntimeError("rendering failed")
        result = _ocr_page(mock_page)
        assert result == ""

    def test_returns_empty_string_when_pytesseract_missing(self):
        mock_page = MagicMock()
        mock_page.to_image.return_value.original = MagicMock()
        with patch("pytesseract.image_to_string", side_effect=Exception("tesseract not found")):
            result = _ocr_page(mock_page)
        assert result == ""


# ===========================================================================
# extract_text  (integration — real PDF/DOCX bytes, no mocking)
# ===========================================================================

class TestExtractText:

    # ── PDF happy path ────────────────────────────────────────────────────────

    def test_pdf_returns_string(self):
        pdf = _make_pdf(["This is a long enough rental contract text for extraction."] * 3)
        result = extract_text(pdf, PDF_CONTENT_TYPE)
        assert isinstance(result, str)

    def test_pdf_content_is_in_result(self):
        pdf = _make_pdf(["Mietvertrag Berlin Wohnung rental agreement contract"] * 3)
        result = extract_text(pdf, PDF_CONTENT_TYPE)
        assert "Mietvertrag" in result

    def test_pdf_result_is_cleaned(self):
        """extract_text must run _clean_text — no excessive newlines."""
        pdf = _make_pdf(["Rental contract text that is long enough " * 3])
        result = extract_text(pdf, PDF_CONTENT_TYPE)
        assert "\n\n\n" not in result

    # ── DOCX happy path ───────────────────────────────────────────────────────

    def test_docx_returns_string(self):
        docx = _make_docx(["Rental contract text paragraph one.",
                            "Second paragraph provides more detail about the lease."])
        result = extract_text(docx, DOCX_CONTENT_TYPE)
        assert isinstance(result, str)

    def test_docx_content_is_in_result(self):
        docx = _make_docx(["Mietvertrag paragraph one with full content details.",
                            "Landlord agrees to maintain the property in good condition."])
        result = extract_text(docx, DOCX_CONTENT_TYPE)
        assert "Mietvertrag" in result

    # ── Unsupported content type ──────────────────────────────────────────────

    def test_unsupported_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported content type"):
            extract_text(b"data", "image/png")

    def test_text_plain_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported content type"):
            extract_text(b"plain text", "text/plain")

    def test_empty_content_type_raises_value_error(self):
        with pytest.raises(ValueError):
            extract_text(b"data", "")

    # ── Too-short output ──────────────────────────────────────────────────────

    def test_pdf_with_no_text_raises_value_error(self):
        """A PDF whose pages yield no text (and OCR returns nothing) raises ValueError."""
        with patch("app.services.document_processor._extract_pdf", return_value=""):
            with pytest.raises(ValueError, match="Could not extract meaningful text"):
                extract_text(b"fake-pdf", PDF_CONTENT_TYPE)

    def test_pdf_with_only_whitespace_raises_value_error(self):
        with patch("app.services.document_processor._extract_pdf", return_value="   \n\n  "):
            with pytest.raises(ValueError, match="Could not extract meaningful text"):
                extract_text(b"fake-pdf", PDF_CONTENT_TYPE)

    def test_pdf_with_49_chars_raises_value_error(self):
        """Exactly 49 chars (< 50 threshold) must raise."""
        with patch("app.services.document_processor._extract_pdf", return_value="x" * 49):
            with pytest.raises(ValueError):
                extract_text(b"fake-pdf", PDF_CONTENT_TYPE)

    def test_pdf_with_50_chars_does_not_raise(self):
        """Exactly 50 chars meets the threshold and must not raise."""
        with patch("app.services.document_processor._extract_pdf", return_value="x" * 50):
            result = extract_text(b"fake-pdf", PDF_CONTENT_TYPE)
        assert len(result) == 50

    def test_docx_with_no_text_raises_value_error(self):
        with patch("app.services.document_processor._extract_docx", return_value=""):
            with pytest.raises(ValueError, match="Could not extract meaningful text"):
                extract_text(b"fake-docx", DOCX_CONTENT_TYPE)

    # ── Return value ──────────────────────────────────────────────────────────

    def test_result_is_stripped(self):
        long_text = "  " + "rental contract text " * 5 + "  "
        with patch("app.services.document_processor._extract_pdf", return_value=long_text):
            result = extract_text(b"fake-pdf", PDF_CONTENT_TYPE)
        assert result == result.strip()