"""验证字段候选证据已正确接入 LangGraph 工作流。"""

from app.agent.research_graph import (
    build_research_graph,
    classify_fields_node,
    initial_research_state,
)
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_registry import (
    RegisteredTool,
    ToolRegistry,
)
from app.agent.tool_schemas import SearchChunksArgs


QUESTION = (
    "Compare document 31 and document 32 "
    "for deepfake detection"
)


def make_evidence(document_id):
    """生成带来源信息的测试证据。"""

    return {
        "document_id": document_id,
        "chunk_id": document_id + 100,
        "title": f"Paper {document_id}",
        "page_start": 2,
        "page_end": 2,
        "content": (
            "The transformer model was evaluated "
            "on the SingFake dataset. "
            "Results demonstrate improved detection."
        ),
    }


def make_graph():
    """创建使用 Mock 工具的可执行工作流。"""

    registry = ToolRegistry()

    registry.register(
        RegisteredTool(
            name="search_chunks",
            description="Search paper chunks",
            args_model=SearchChunksArgs,
            handler=lambda args: [
                make_evidence(args.document_id)
            ],
        )
    )

    executor = ToolExecutor(
        registry,
        max_calls=5,
    )

    return build_research_graph(
        executor=executor,
        enable_supplement=False,
    )


def test_field_node_detects_three_candidate_types():
    """字段节点可以从真实结构的 Chunk 识别三类候选。"""

    state = initial_research_state(QUESTION)
    state["evidence"] = [make_evidence(31)]

    result = classify_fields_node(state)

    candidates = result["field_candidates"]

    assert len(candidates["method"]) == 1
    assert len(candidates["experimental_conditions"]) == 1
    assert len(candidates["conclusion"]) == 1


def test_graph_classifies_evidence_from_both_papers():
    """两个论文的证据均应参与字段分类。"""

    result = make_graph().invoke(
        initial_research_state(QUESTION)
    )

    assert result["tool_calls"] == 2

    methods = result["field_candidates"]["method"]

    assert {
        item["reference"]["document_id"]
        for item in methods
    } == {31, 32}


def test_classification_does_not_claim_support():
    """关键词分类不能直接生成已验证的研究结论。"""

    result = make_graph().invoke(
        initial_research_state(QUESTION)
    )

    assert len(result["field_candidates"]["conclusion"]) == 2

    for row in result["evidence_matrix"]:
        assert row["method"]["status"] == "insufficient"
        assert row["experimental_conditions"]["status"] == "insufficient"
        assert row["conclusion"]["status"] == "insufficient"

        assert row["method"]["value"] is None
        assert row["method"]["references"] == []


def test_planning_failure_skips_field_classification():
    """没有合法检索计划时不得生成候选字段。"""

    result = make_graph().invoke(
        initial_research_state(
            "Compare two unknown papers"
        )
    )

    assert result["field_candidates"] == {}
    assert result["tool_calls"] == 0

    assert [
        step["step"]
        for step in result["steps"]
    ] == ["plan", "answer"]