"""执行规则检索计划，统一返回候选结果和工具执行日志。"""

from dataclasses import dataclass, field
from time import perf_counter
from typing import Literal, Mapping, TypeVar
from collections.abc import Callable

from app.schemas.search import SearchResult
from app.services.retrievers import Retriever
from app.services.search_router import SearchPlan, SearchRequest, SearchRouter
from app.services.rrf_fusion import reciprocal_rank_fusion, result_key


T = TypeVar("T")


def direct_retrieval_runner(operation: Callable[[], T]) -> T:
    """默认直接执行检索，方便纯逻辑单元测试。"""

    return operation()

@dataclass(frozen=True)
class RetrievalExecution:
    """记录单个 Retriever 的实际执行状态。"""

    retriever: str
    status: Literal["success", "failed", "not_configured"]
    result_count: int
    elapsed_ms: float
    error_type: str | None = None


@dataclass
class OrchestratedSearchResponse:
    """统一存储检索结果、策略和执行日志。"""

    planner: str
    selected_retrievers: list[str]
    results: list[SearchResult] = field(default_factory=list)
    execution_log: list[RetrievalExecution] = field(default_factory=list)
    candidate_sources: dict[str, list[str]] = field(default_factory=dict)
    fusion_method: str | None = None


class SearchOrchestrator:
    """根据规则计划执行检索，不调用 LLM。"""

    def __init__(
        self,
        retrievers: Mapping[str, Retriever],
        router: SearchRouter | None = None,
        retrieval_runner: Callable[
            [Callable[[], list[SearchResult]]],
            list[SearchResult],
        ] | None = None,
    ):
        self.retrievers = dict(retrievers)
        self.router = router or SearchRouter()
        self.retrieval_runner = (
            retrieval_runner or direct_retrieval_runner
        )

    def execute(
        self,
        request: SearchRequest,
    ) -> OrchestratedSearchResponse:
        """执行检索计划，记录每个工具的真实执行状态。"""

        plan: SearchPlan = self.router.select(request)

        response = OrchestratedSearchResponse(
            planner=plan.planner,
            selected_retrievers=list(plan.retrievers),
        )

        successful_results: dict[str, list[SearchResult]] = {}

        for name in plan.retrievers:
            retriever = self.retrievers.get(name)

            if retriever is None:
                response.execution_log.append(
                    RetrievalExecution(
                        retriever=name,
                        status="not_configured",
                        result_count=0,
                        elapsed_ms=0.0,
                    )
                )
                continue

            start = perf_counter()

            try:
                kwargs = {
                    "document_id": request.document_id,
                    "limit": request.limit,
                }

                if name == "metadata":
                    if request.title is not None:
                        kwargs["title"] = request.title

                    if request.doi is not None:
                        kwargs["doi"] = request.doi

                # 每个 Retriever 的完整执行过程由 runner 单独保护。
                results = self.retrieval_runner(
                    lambda: retriever.retrieve(
                        request.query,
                        **kwargs,
                    )
                )

                # 检索器只能返回统一 Schema，不接受伪造的成功结果。
                if not isinstance(results, list) or not all(
                    isinstance(item, SearchResult)
                    for item in results
                ):
                    raise TypeError(
                        f"{name} returned invalid search results"
                    )

            except Exception as exc:
                response.execution_log.append(
                    RetrievalExecution(
                        retriever=name,
                        status="failed",
                        result_count=0,
                        elapsed_ms=(perf_counter() - start) * 1000,
                        error_type=type(exc).__name__,
                    )
                )
                continue

            successful_results[name] = results

            response.execution_log.append(
                RetrievalExecution(
                    retriever=name,
                    status="success",
                    result_count=len(results),
                    elapsed_ms=(perf_counter() - start) * 1000,
                )
            )

        # 仅记录实际成功返回的候选来源。
        candidate_sources: dict[str, list[str]] = {}

        for name, results in successful_results.items():
            for result in results:
                key = ":".join(
                    str(part) for part in result_key(result)
                )

                sources = candidate_sources.setdefault(key, [])

                if name not in sources:
                    sources.append(name)

        # 只保留最终返回的候选对应的来源。
        if len(successful_results) >= 2:
            response.results = reciprocal_rank_fusion(
                successful_results,
                limit=request.limit,
            )
            response.fusion_method = "rrf"
        elif len(successful_results) == 1:
            response.results = list(
                next(iter(successful_results.values()))
            )[:request.limit]
        else:
            response.results = []

        response.candidate_sources = {
            ":".join(str(part) for part in result_key(result)):
            candidate_sources[
                ":".join(str(part) for part in result_key(result))
            ]
            for result in response.results
        }

        return response