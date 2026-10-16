"""定义论文检索的标准化结果结构。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SearchResult(BaseModel):
    """统一表示论文、Chunk 或章节检索结果。"""

    model_config = ConfigDict(from_attributes=True)

    document_id: int
    title: str

    chunk_id: int | None = None
    page_start: int | None = None
    page_end: int | None = None

    content: str | None = None
    score: float | None = None

    retrieval_source: Literal[
        "metadata",
        "postgres_fts",
        "postgres_literal",
        "paper_section",
    ]

    section_id: int | None = None
    section_heading: str | None = None
    verification_status: str | None = None