
from collections.abc import Sequence

from app.models.document import DocumentPage


def find_chunk_page_range(start_char: int,end_char: int,pages: Sequence[DocumentPage],) -> tuple[int | None, int | None]:
    """
    Return PDF page numbers overlapping a chunk.

    All character offsets are half-open: [start, end).
    Page separators do not count as page text.
    """
    if start_char < 0 or end_char <= start_char:
        raise ValueError("Invalid chunk character range")

    matched = [
        page.page_number
        for page in pages
        if start_char < page.end_char
        and end_char > page.start_char
    ]

    if not matched:
        return None, None

    return min(matched), max(matched)
