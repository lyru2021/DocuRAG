"""证据一致性校验服务。

用于确认 chunk 文本、字符偏移和 PDF 页码映射是否彼此一致。
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.models.document import Chunk, DocumentPage
from app.services.page_mapper import find_chunk_page_range


@dataclass(frozen=True)
class EvidenceValidation:
    """chunk 证据一致性的校验结果。"""

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
    """验证 chunk 文本、字符偏移和页码范围是否互相一致。

    Args:
        full_text: 文档解析后保存的完整文本。
        chunk: 待验证的 chunk 记录。
        pages: 同一文档下的 PDF 页面映射记录。

    Returns:
        EvidenceValidation: 文本校验、页码校验和整体校验的布尔结果。

    Notes:
        这里不只验证 chunk 文本，还会验证页面记录本身是否能从全文切回原内容；
        否则错误的页面映射可能让 evidence 指向错误页码。
    """

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
    # 先校验页面记录本身，避免后续页码判断建立在错误的页偏移上。
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
    # 持久化页码必须与实时计算结果完全一致，才能认为 evidence 可追溯。
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
