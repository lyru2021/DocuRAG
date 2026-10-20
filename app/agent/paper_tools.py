"""将科研 Agent 的白名单工具绑定到真实 PostgreSQL 检索服务。"""
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tool_registry import RegisteredTool, ToolRegistry
from app.agent.tool_schemas import (
    GetEvidenceArgs,
    SearchChunksArgs,
    SearchPapersArgs,
)
from app.models.document import Chunk, Document
from app.schemas.search import SearchResult
from app.services.search_service import SearchService


class EvidenceNotFoundError(LookupError):
    """请求的证据不存在，或不属于指定的已解析论文。"""


def get_evidence(
    db: Session,
    args: GetEvidenceArgs,
) -> SearchResult:
    """按真实数据库 ID 读取已解析论文的指定 Chunk。"""

    row = db.execute(
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Chunk.id == args.chunk_id,
            Chunk.document_id == args.document_id,
            Document.parse_status == "parsed",
        )
    ).one_or_none()

    if row is None:
        raise EvidenceNotFoundError(
            "evidence not found for the specified document and chunk"
        )

    chunk, document = row

    return SearchResult(
        document_id=document.id,
        title=document.title,
        chunk_id=chunk.id,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        content=chunk.content,
        score=None,
        retrieval_source="postgres_literal",
    )


def build_paper_tool_registry(
    session_factory: Callable[[], AbstractContextManager[Session]],
) -> ToolRegistry:
    """让每次工具执行在独立、受控的数据库上下文中完成。"""

    registry = ToolRegistry()

    def search_papers_handler(args: SearchPapersArgs):
        """在短事务内查询论文元数据。"""

        with session_factory() as db:
            service = SearchService(db)

            return service.search_papers(
                document_id=args.document_id,
                title=args.title,
                doi=args.doi,
                author=args.author,
                year=args.year,
                limit=args.limit,
            )

    def search_chunks_handler(args: SearchChunksArgs):
        """在短事务内检索已解析论文的正文。"""

        with session_factory() as db:
            service = SearchService(db)

            return service.search_chunks(
                args.query,
                mode=args.mode,
                document_id=args.document_id,
                limit=args.limit,
            )

    def get_evidence_handler(args: GetEvidenceArgs):
        """在短事务内精确读取数据库中的 Chunk。"""

        with session_factory() as db:
            return get_evidence(db, args)

    registry.register(
        RegisteredTool(
            name="search_papers",
            description=(
                "Search stored academic papers by document ID, "
                "title, DOI, author, or publication year."
            ),
            args_model=SearchPapersArgs,
            handler=search_papers_handler,
        )
    )

    registry.register(
        RegisteredTool(
            name="search_chunks",
            description=(
                "Search parsed paper text using literal matching "
                "or PostgreSQL full-text search."
            ),
            args_model=SearchChunksArgs,
            handler=search_chunks_handler,
        )
    )

    registry.register(
        RegisteredTool(
            name="get_evidence",
            description=(
                "Retrieve exact stored evidence using "
                "document_id and chunk_id."
            ),
            args_model=GetEvidenceArgs,
            handler=get_evidence_handler,
        )
    )

    return registry