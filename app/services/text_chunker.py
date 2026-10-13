from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
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
    """

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
