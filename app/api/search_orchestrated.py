"""提供带策略选择、候选来源和执行记录的检索 API。"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.search import SearchResult
from app.services.retrievers import KeywordRetriever, MetadataRetriever
from app.services.search_orchestrator import SearchOrchestrator
from app.services.search_router import SearchRequest
from app.services.search_service import SearchService
from app.services.retrieval_transaction import run_with_savepoint




router = APIRouter(tags=["search"])


class OrchestratedSearchRequest(BaseModel):
    """编排检索请求。"""

    query: str = Field(default="", max_length=500)
    document_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    doi: str | None = Field(default=None, min_length=1, max_length=255)
    strategy: Literal[
        "auto", "metadata", "literal", "fts", "hybrid"
    ] = "auto"
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_strategy(self):
        """提前拒绝无法执行的检索条件。"""

        if self.strategy == "hybrid":
            if not self.query.strip():
                raise ValueError("hybrid requires query")
            if self.title is not None or self.doi is not None:
                raise ValueError("hybrid does not support title or doi")

        if self.strategy in {"literal", "fts"}:
            if not self.query.strip():
                raise ValueError("keyword search requires query")
            if self.title is not None or self.doi is not None:
                raise ValueError(
                    "keyword search does not support title or doi"
                )

        if self.strategy == "auto":
            if (
                not self.query.strip()
                and self.document_id is None
                and self.title is None
                and self.doi is None
            ):
                raise ValueError("search criteria required")

        if self.strategy == "metadata":
            if (
                self.document_id is None
                and self.title is None
                and self.doi is None
            ):
                raise ValueError("metadata filter required")

        return self


class RetrievalExecutionResponse(BaseModel):
    """单个检索器的执行记录。"""

    retriever: str
    status: Literal["success", "failed", "not_configured"]
    result_count: int
    elapsed_ms: float
    error_type: str | None = None


class OrchestratedSearchResponseSchema(BaseModel):
    """统一 HTTP 编排检索响应。"""

    planner: str
    selected_retrievers: list[str]
    results: list[SearchResult]
    execution_log: list[RetrievalExecutionResponse]
    candidate_sources: dict[str, list[str]]
    fusion_method: str | None = None


@router.post(
    "/search/orchestrated",
    response_model=OrchestratedSearchResponseSchema,
)
def orchestrated_search(
    payload: OrchestratedSearchRequest,
    db: Session = Depends(get_db),
):
    """根据确定性规则实际执行检索并返回证据与执行日志。"""

    service = SearchService(db)

    orchestrator = SearchOrchestrator(
        {
            "metadata": MetadataRetriever(service),
            "keyword_literal": KeywordRetriever(service, mode="literal"),
            "keyword_fts": KeywordRetriever(service, mode="fts"),
        },
        retrieval_runner=lambda operation: run_with_savepoint(db,operation),
    )

    request = SearchRequest(
        query=payload.query,
        document_id=payload.document_id,
        title=payload.title,
        doi=payload.doi,
        strategy=payload.strategy,
        limit=payload.limit,
    )

    response = orchestrator.execute(request)

    return OrchestratedSearchResponseSchema(
        planner=response.planner,
        selected_retrievers=response.selected_retrievers,
        results=response.results,
        execution_log=[
            RetrievalExecutionResponse(
                retriever=log.retriever,
                status=log.status,
                result_count=log.result_count,
                elapsed_ms=log.elapsed_ms,
                error_type=log.error_type,
            )
            for log in response.execution_log
        ],
        candidate_sources=response.candidate_sources,
        fusion_method=response.fusion_method,
    )