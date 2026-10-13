from app.models.document import Chunk, DocumentPage
from app.services.evidence_validator import validate_evidence


def make_page(number, text, start):
    return DocumentPage(
        page_number=number,
        content=text,
        start_char=start,
        end_char=start + len(text),
    )


def make_chunk(text, start, end, page_start, page_end):
    return Chunk(
        chunk_index=0,
        content=text[start:end],
        start_char=start,
        end_char=end,
        page_start=page_start,
        page_end=page_end,
    )


def test_valid_single_page_evidence():
    text = "Introduction to scientific research."

    page = make_page(1, text, 0)
    chunk = make_chunk(text, 0, 12, 1, 1)

    result = validate_evidence(text, chunk, [page])

    assert result.verified is True
    assert result.text_verified is True
    assert result.pages_verified is True


def test_valid_cross_page_evidence():
    first = "First page content."
    second = "Second page content."

    text = first + "\n\n" + second

    pages = [
        make_page(1, first, 0),
        make_page(2, second, len(first) + 2),
    ]

    start = len(first) - 5
    end = len(first) + 7

    chunk = make_chunk(text, start, end, 1, 2)

    result = validate_evidence(text, chunk, pages)

    assert result.verified is True
    assert result.page_start == 1
    assert result.page_end == 2


def test_incorrect_page_mapping_is_rejected():
    text = "A scientific paper."

    page = make_page(1, text, 0)
    chunk = make_chunk(text, 0, 10, 2, 2)

    result = validate_evidence(text, chunk, [page])

    assert result.text_verified is True
    assert result.pages_verified is False
    assert result.verified is False


def test_tampered_page_text_is_rejected():
    text = "Original scientific text."

    page = make_page(1, "Changed content", 0)
    chunk = make_chunk(text, 0, 10, 1, 1)

    result = validate_evidence(text, chunk, [page])

    assert result.pages_verified is False
    assert result.verified is False
