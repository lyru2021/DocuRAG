"""提供论文元数据过滤与正文检索 API。"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.search import SearchResult
from app.services.search_service import SearchService


router = APIRouter(tags=["search"])


class ChunkSearchRequest(BaseModel):
    """正文检索请求。"""

    query: str = Field(min_length=1, max_length=500)
    mode: Literal["literal", "fts"] = "literal"
    document_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=20, ge=1, le=100)


@router.get(
    "/papers/search",
    response_model=list[SearchResult],
)
def search_papers(
    document_id: int | None = Query(default=None, gt=0),
    title: str | None = None,
    author: str | None = None,
    year: int | None = Query(default=None, ge=1000, le=2100),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """按论文元数据组合过滤。"""

    return SearchService(db).search_papers(
        document_id=document_id,
        title=title,
        author=author,
        year=year,
        limit=limit,
    )


@router.post(
    "/search",
    response_model=list[SearchResult],
)
def search_chunks(
    payload: ChunkSearchRequest,
    db: Session = Depends(get_db),
):
    """检索论文正文并返回原始证据。"""

    return SearchService(db).search_chunks(
        payload.query,
        mode=payload.mode,
        document_id=payload.document_id,
        limit=payload.limit,
    )