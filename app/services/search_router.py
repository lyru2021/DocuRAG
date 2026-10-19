"""根据显式条件和查询文本选择检索策略。"""

from dataclasses import dataclass
from typing import Literal


RetrieverName = Literal[
    "metadata",
    "keyword_literal",
    "keyword_fts",
]


@dataclass(frozen=True)
class SearchRequest:
    """表示检索请求及显式过滤条件。"""

    query: str = ""
    document_id: int | None = None
    title: str | None = None
    doi: str | None = None
    strategy: Literal["auto", "metadata", "literal", "fts", "hybrid"] = "auto"
    limit: int = 20


@dataclass(frozen=True)
class SearchPlan:
    """记录规则路由的结果及选择原因。"""

    retrievers: tuple[RetrieverName, ...]
    reason: str
    planner: str = "rule_based"


class SearchRouter:
    """使用确定性规则选择检索器，不调用 LLM。"""

    def select(self, request: SearchRequest) -> SearchPlan:
        """生成检索计划，但不执行实际查询。"""

        if request.limit < 1:
            raise ValueError("limit must be positive")

        query = request.query.strip()

        if request.strategy == "hybrid":
            if not query:
                raise ValueError(
                    "hybrid strategy requires a query"
                )

            if request.title is not None or request.doi is not None:
                raise ValueError(
                    "hybrid strategy does not support title or doi filters"
                )

            return SearchPlan(
                retrievers=(
                    "keyword_literal",
                    "keyword_fts",
                ),
                reason="explicit_hybrid_strategy",
            )

        if request.strategy == "metadata":
            if (
                request.document_id is None
                and not request.title
                and not request.doi
            ):
                raise ValueError(
                    "metadata strategy requires document_id, title or doi"
                )

            return SearchPlan(
                retrievers=("metadata",),
                reason="explicit_metadata_strategy",
            )

        if request.strategy == "literal":
            if not query:
                raise ValueError("literal strategy requires a query")

            return SearchPlan(
                retrievers=("keyword_literal",),
                reason="explicit_literal_strategy",
            )

        if request.strategy == "fts":
            if not query:
                raise ValueError("fts strategy requires a query")

            return SearchPlan(
                retrievers=("keyword_fts",),
                reason="explicit_fts_strategy",
            )

        if request.strategy != "auto":
            raise ValueError("unsupported search strategy")

        if request.doi is not None:
            if not request.doi.strip():
                raise ValueError("doi must not be empty")

            return SearchPlan(
                retrievers=("metadata",),
                reason="explicit_doi_filter",
            )

        if request.title:
            return SearchPlan(
                retrievers=("metadata",),
                reason="explicit_title_filter",
            )

        if not query:
            if request.document_id is not None:
                return SearchPlan(
                    retrievers=("metadata",),
                    reason="document_id_lookup",
                )

            raise ValueError(
                "auto strategy requires query or metadata filter"
            )

        if any("\u4e00" <= char <= "\u9fff" for char in query):
            return SearchPlan(
                retrievers=("keyword_literal",),
                reason="chinese_keyword",
            )

        return SearchPlan(
            retrievers=("keyword_fts",),
            reason="english_keyword",
        )