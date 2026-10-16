
"""字符区间到 PDF 页码区间的映射工具。"""

from collections.abc import Sequence

from app.models.document import DocumentPage


def find_chunk_page_range(
    start_char: int,
    end_char: int,
    pages: Sequence[DocumentPage],
) -> tuple[int | None, int | None]:
    """
    Return PDF page numbers overlapping a chunk.

    All character offsets are half-open: [start, end).
    Page separators do not count as page text.

    Args:
        start_char: chunk 在合并全文中的起始位置，包含该字符。
        end_char: chunk 在合并全文中的结束位置，不包含该字符。
        pages: PDF 页面文本在合并全文中的字符区间。

    Returns:
        tuple[int | None, int | None]: 命中的起止页码；没有页面重叠时返回 `(None, None)`。

    Raises:
        ValueError: chunk 字符区间非法。
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
