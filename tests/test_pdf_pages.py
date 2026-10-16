"""PDF 页面文本和全文偏移映射测试。"""

import fitz

from app.services.document_parser import (
    parse_pdf_with_pages,
)


def make_pdf(page_texts: list[str]) -> bytes:
    pdf = fitz.open()

    for text in page_texts:
        page = pdf.new_page()

        if text:
            page.insert_text((72, 72), text)

    data = pdf.tobytes()
    pdf.close()
    return data


def test_pdf_page_mapping():
    data = make_pdf([
        "First page content",
        "Second page content",
        "Third page content",
    ])

    result = parse_pdf_with_pages(data)

    assert len(result.pages) == 3

    assert [
        page.page_number for page in result.pages
    ] == [1, 2, 3]

    assert result.text == (
        "First page content\n\n"
        "Second page content\n\n"
        "Third page content"
    )

    for page in result.pages:
        assert result.text[
            page.start_char:page.end_char
        ] == page.text


def test_pdf_empty_middle_page():
    data = make_pdf([
        "Page one",
        "",
        "Page three",
    ])

    result = parse_pdf_with_pages(data)

    assert [
        page.page_number for page in result.pages
    ] == [1, 3]

    assert result.text == "Page one\n\nPage three"


def test_pdf_page_offsets_include_separator():
    data = make_pdf([
        "Alpha",
        "Bravo",
    ])

    result = parse_pdf_with_pages(data)

    first, second = result.pages

    assert first.start_char == 0
    assert first.end_char == 5

    assert second.start_char == 7
    assert second.end_char == 12

    assert result.text[5:7] == "\n\n"
