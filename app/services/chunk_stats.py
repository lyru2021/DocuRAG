from dataclasses import dataclass
from statistics import mean

from app.services.text_chunker import TextChunk


@dataclass(frozen=True)
class ChunkStats:
    chunk_count: int
    total_chunk_chars: int
    min_length: int
    max_length: int
    avg_length: float


def calculate_chunk_stats(
    chunks: list[TextChunk],
) -> ChunkStats:
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
