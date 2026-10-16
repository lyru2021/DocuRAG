"""在独立 JSON 实验快照上执行确定性关键词检索。"""

from app.evaluation.metrics import RankedChunk


def search_snapshot(
    snapshot: dict,
    query: str,
    limit: int = 5,
) -> list[RankedChunk]:
    """按字面子串匹配 Chunk，并使用稳定排序。"""

    query = query.strip()

    if not query:
        raise ValueError("query must not be empty")

    if limit < 1:
        raise ValueError("limit must be positive")

    matches = []
    term = query.casefold()

    for paper in snapshot["papers"]:
        for chunk in paper["chunks"]:
            if term in chunk["content"].casefold():
                matches.append(
                    RankedChunk(
                        document_id=paper["document_id"],
                        chunk_index=chunk["chunk_index"],
                        start_char=chunk["start_char"],
                        end_char=chunk["end_char"],
                    )
                )

    matches.sort(
        key=lambda chunk: (
            chunk.document_id,
            chunk.chunk_index,
            chunk.start_char,
        )
    )

    return matches[:limit]