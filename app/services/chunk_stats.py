"""chunk 长度统计工具。"""

from dataclasses import dataclass
from statistics import mean

from app.services.text_chunker import TextChunk


@dataclass(frozen=True)
class ChunkStats:
    """一组 chunk 的长度统计结果。"""

    chunk_count: int
    total_chunk_chars: int
    min_length: int
    max_length: int
    avg_length: float


def calculate_chunk_stats(
    chunks: list[TextChunk],
) -> ChunkStats:
    """计算 chunk 长度分布。

    Args:
        chunks: `split_text()` 生成的 chunk 列表。

    Returns:
        ChunkStats: chunk 数量、总字符数、最短/最长长度和平均长度。
    """

    lengths = [len(chunk.content) for chunk in chunks]

    if not lengths:
        return ChunkStats(
            chunk_count=0,
            total_chunk_chars=0,
            min_length=0,
            max_length=0,
            avg_length=0.0,
        )

    return ChunkStats(
        chunk_count=len(chunks),
        total_chunk_chars=sum(lengths),
        min_length=min(lengths),
        max_length=max(lengths),
        avg_length=mean(lengths),
    )
