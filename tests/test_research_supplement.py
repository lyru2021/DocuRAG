"""验证补检任务规划、次数上限及共享执行预算。"""

from app.agent.research_graph import (
    build_research_graph,
    initial_research_state,
)
from app.agent.research_supplement import (
    plan_supplementary_tasks,
)
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_registry import RegisteredTool, ToolRegistry
from app.agent.tool_schemas import SearchChunksArgs


QUESTION = (
    "Compare document 31 and document 32 "
    "for deepfake detection"
)


def make_executor(max_calls=5):
    """模拟两个论文的初检和补检。"""

    registry = ToolRegistry()

    def handler(args):
        return [{
            "document_id": args.document_id,
            "chunk_id": (
                args.document_id * 100
                + (1 if args.query == "detection" else 2)
            ),
            "title": f"Paper {args.document_id}",
            "page_start": 1,
            "page_end": 1,
            "content": (
                "The model was evaluated on a dataset. "
                "Results demonstrate improved detection."
            ),
        }]

    registry.register(
        RegisteredTool(
            name="search_chunks",
            description="Search paper evidence",
            args_model=SearchChunksArgs,
            handler=handler,
        )
    )

    return ToolExecutor(registry, max_calls=max_calls)


def test_supplement_planner_targets_missing_fields():
    """补检任务只针对明确缺失的字段。"""

    tasks = plan_supplementary_tasks({
        31: ["experimental_conditions"],
    })

    assert len(tasks) == 1
    assert tasks[0]["arguments"]["document_id"] == 31
    assert tasks[0]["arguments"]["query"] == "dataset"


def test_supplement_planner_limits_tasks():
    """补检任务数不能超过规划上限。"""

    tasks = plan_supplementary_tasks(
        {
            31: ["method", "experimental_conditions", "conclusion"],
            32: ["method", "experimental_conditions", "conclusion"],
        },
        max_tasks=3,
    )

    assert len(tasks) == 3


def test_graph_runs_one_supplementary_round():
    """证据不足时最多进行一轮补检。"""

    executor = make_executor()

    result = build_research_graph(executor).invoke(
        initial_research_state(QUESTION)
    )

    assert result["supplementary_searches"] == 1
    assert result["tool_calls"] <= 5

    assert any(
        step["step"] == "supplement"
        for step in result["steps"]
    )


def test_supplement_uses_shared_tool_budget():
    """初检与补检不能分别获得独立预算。"""

    executor = make_executor(max_calls=2)

    result = build_research_graph(executor).invoke(
        initial_research_state(QUESTION)
    )

    assert result["tool_calls"] == 2
    assert result["supplementary_searches"] == 1

    assert any(
        "Shared tool budget exhausted" in step["detail"]
        for step in result["steps"]
    )


def test_supplement_preserves_original_evidence():
    """补检不得丢弃初检取得的候选证据。"""

    executor = make_executor()

    result = build_research_graph(executor).invoke(
        initial_research_state(QUESTION)
    )

    ids = {
        item["document_id"]
        for item in result["evidence"]
    }

    assert ids == {31, 32}
    assert result["status"] == "insufficient_evidence"
    assert result["answer"] == "未找到充分证据"


def test_supplement_round_robin_between_papers():
    """补检任务应在不同论文之间轮流分配。"""

    tasks = plan_supplementary_tasks(
        {
            31: [
                "method",
                "experimental_conditions",
                "conclusion",
            ],
            32: [
                "method",
                "experimental_conditions",
                "conclusion",
            ],
        },
        max_tasks=3,
    )

    assert [
        task["arguments"]["document_id"]
        for task in tasks
    ] == [31, 32, 31]

    assert [
        task["arguments"]["query"]
        for task in tasks
    ] == ["model", "model", "dataset"]


def test_supplement_handles_uneven_missing_fields():
    """一篇论文缺失字段较少时，剩余名额仍可分配。"""

    tasks = plan_supplementary_tasks(
        {
            31: ["method"],
            32: [
                "method",
                "experimental_conditions",
                "conclusion",
            ],
        },
        max_tasks=3,
    )

    assert [
        task["arguments"]["document_id"]
        for task in tasks
    ] == [31, 32, 32]


def test_supplement_deduplicates_fields():
    """重复缺失字段不应导致重复补检。"""

    tasks = plan_supplementary_tasks(
        {
            31: ["method", "method", "method"],
            32: ["conclusion"],
        },
        max_tasks=3,
    )

    assert len(tasks) == 2

    assert [
        task["arguments"]["query"]
        for task in tasks
    ] == ["model", "results"]


def test_supplement_filters_invalid_targets():
    """非法文档与未知字段不应消耗补检预算。"""

    tasks = plan_supplementary_tasks(
        {
            -1: ["method"],
            31: ["unknown_field", "conclusion"],
            32: ["experimental_conditions"],
        },
        max_tasks=3,
    )

    assert len(tasks) == 2

    assert [
        task["arguments"]["document_id"]
        for task in tasks
    ] == [31, 32]

    assert [
        task["arguments"]["query"]
        for task in tasks
    ] == ["results", "dataset"]