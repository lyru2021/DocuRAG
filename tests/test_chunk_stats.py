"""chunk 长度统计测试。"""

from app.services.chunk_stats import calculate_chunk_stats
from app.services.text_chunker import split_text


def test_chunk_stats_300():
    chunks = split_text("A" * 1000, 300, 50)

    stats = calculate_chunk_stats(chunks)

    assert stats.chunk_count == 4
    assert stats.min_length == 250
    assert stats.max_length == 300
    assert stats.total_chunk_chars == 1150
    assert stats.avg_length == 287.5


def test_chunk_stats_empty():
    stats = calculate_chunk_stats([])

    assert stats.chunk_count == 0
    assert stats.avg_length == 0.0
    assert stats.total_chunk_chars == 0


def test_chunk_stats_500():
    chunks = split_text("B" * 1000, 500, 50)

    stats = calculate_chunk_stats(chunks)

    assert stats.chunk_count == 3
    assert stats.total_chunk_chars == 1100
    assert stats.min_length == 100
    assert stats.max_length == 500
