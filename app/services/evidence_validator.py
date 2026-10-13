from collections.abc import Sequence
from dataclasses import dataclass

from app.models.document import Chunk, DocumentPage
from app.services.page_mapper import find_chunk_page_range


@dataclass(frozen=True)
class EvidenceValidation:
    verified: bool
    text_verified: bool
    pages_verified: bool
    page_start: int | None
    page_end: int | None


def validate_evidence(
    full_text: str,
    chunk: Chunk,
    pages: Sequence[DocumentPage],
) -> EvidenceValidation:
    start = chunk.start_char
    end = chunk.end_char

    valid_offsets = (
        isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start < end <= len(full_text)
    )

    text_verified = (
        valid_offsets
        and full_text[start:end] == chunk.content
    )

    # Ensure every stored page has text consistent
    # with its global character interval.
    stored_pages_valid = all(
        isinstance(page.start_char, int)
        and isinstance(page.end_char, int)
        and 0 <= page.start_char < page.end_char <= len(full_text)
        and full_text[
            page.start_char:page.end_char
        ] == page.content
        for page in pages
    )

    expected_start = None
    expected_end = None

    if valid_offsets and pages and stored_pages_valid:
        expected_start, expected_end = find_chunk_page_range(
            start,
            end,
            pages,
        )

    # Verify that the persisted page range is exactly
    # what the stored page intervals indicate.
    pages_verified = (
        bool(pages)
        and stored_pages_valid
        and expected_start is not None
        and chunk.page_start == expected_start
        and chunk.page_end == expected_end
    )

    return EvidenceValidation(
        verified=bool(text_verified and pages_verified),
        text_verified=bool(text_verified),
        pages_verified=bool(pages_verified),
        page_start=expected_start,
        page_end=expected_end,
    )
