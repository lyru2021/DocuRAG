"""基于字符窗口的文本分块工具。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    """文本分块结果。

    字符区间使用 Python 半开区间 `[start_char, end_char)`，
    便于直接用 `text[start_char:end_char]` 校验证据。
    """

    chunk_index: int
    content: str
    start_char: int
    end_char: int


def split_text(
    text: str,
    chunk_size: int = 300,
    overlap: int = 50,
) -> list[TextChunk]:
    """
    Split text using overlapping character windows.

    Positions use Python string indices:
    - start_char: inclusive
    - end_char: exclusive

    The returned positions refer to the input text.

    Args:
        text: 待分块的完整文本。
        chunk_size: 单个 chunk 的最大字符数。
        overlap: 相邻 chunk 之间保留的重叠字符数。

    Returns:
        list[TextChunk]: 按原文顺序排列的非空 chunk。

    Raises:
        ValueError: `chunk_size` 或 `overlap` 类型/取值不合法。
    """

    # bool 是 int 的子类，显式排除可以避免 True/False 被误当作 1/0。
    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool):
        raise ValueError("chunk_size must be an integer")

    if not isinstance(overlap, int) or isinstance(overlap, bool):
        raise ValueError("overlap must be an integer")

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must satisfy 0 <= overlap < chunk_size"
        )

    if not text:
        return []

    step = chunk_size - overlap
    chunks = []

    for start in range(0, len(text), step):
        end = min(start + chunk_size, len(text))
        content = text[start:end]

        if content.strip():
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    content=content,
                    start_char=start,
                    end_char=end,
                )
            )

        if end == len(text):
            break

    return chunks
