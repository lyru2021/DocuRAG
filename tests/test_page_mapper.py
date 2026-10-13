from app.models.document import DocumentPage
from app.services.page_mapper import find_chunk_page_range


def make_page(number, start, end):
    return DocumentPage(
        page_number=number,
        content="X" * (end - start),
        start_char=start,
        end_char=end,
    )


def test_chunk_on_one_page():
    pages = [
        make_page(1, 0, 100),
        make_page(2, 102, 200),
    ]

    assert find_chunk_page_range(
        10, 80, pages
    ) == (1, 1)


def test_chunk_spans_two_pages():
    pages = [
        make_page(1, 0, 100),
        make_page(2, 102, 200),
    ]

    assert find_chunk_page_range(
        80, 150, pages
    ) == (1, 2)


def test_chunk_only_in_page_separator():
    pages = [
        make_page(1, 0, 100),
        make_page(2, 102, 200),
    ]

    assert find_chunk_page_range(
        100, 102, pages
    ) == (None, None)


def test_empty_page_mapping():
    assert find_chunk_page_range(
        0, 50, []
    ) == (None, None)
