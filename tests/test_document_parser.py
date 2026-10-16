"""TXT/PDF 文档解析服务测试。"""

import fitz
import pytest

from app.services.document_parser import (
    DocumentParseError,
    clean_text,
    parse_pdf,
    parse_txt,
)


def test_clean_text_preserves_paragraphs():
    raw = "第一段  内容\r\n\r\n\r\n第二段  内容"

    result = clean_text(raw)

    assert result == "第一段 内容\n\n第二段 内容"


def test_parse_valid_txt():
    data = "Hello\n\nFastAPI Knowledge Base".encode("utf-8")

    result = parse_txt(data)

    assert result == "Hello\n\nFastAPI Knowledge Base"


def test_parse_empty_txt():
    with pytest.raises(
        DocumentParseError,
        match="no readable text",
    ):
        parse_txt(b"")


def test_parse_invalid_encoding():
    with pytest.raises(
        DocumentParseError,
        match="UTF-8",
    ):
        parse_txt(b"\xff\xfe\xfa")


def test_parse_valid_pdf():
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Hello DocuRAG")

    data = pdf.tobytes()
    pdf.close()

    result = parse_pdf(data)

    assert "Hello DocuRAG" in result


def test_parse_pdf_without_text():
    pdf = fitz.open()
    pdf.new_page()

    data = pdf.tobytes()
    pdf.close()

    with pytest.raises(
        DocumentParseError,
        match="No extractable text",
    ):
        parse_pdf(data)


def test_parse_invalid_pdf():
    with pytest.raises(DocumentParseError):
        parse_pdf(b"This is not a PDF")
