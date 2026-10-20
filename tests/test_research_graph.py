"""验证 LangGraph 状态初始化、节点顺序和无证据降级。"""

import pytest

from app.agent.research_graph import (
    build_research_graph,
    initial_research_state,
)


def test_initial_state_contains_all_fields():
    """初始状态必须包含检索、证据与执行记录字段。"""

    state = initial_research_state(
        "Compare two deepfake detection papers"
    )

    assert state["retrieval_plan"] == []
    assert state["evidence"] == []
    assert state["evidence_matrix"] == []
    assert state["tool_calls"] == 0
    assert state["supplementary_searches"] == 0
    assert state["status"] == "pending"


def test_blank_question_is_rejected():
    """空白研究问题不得进入工作流。"""

    with pytest.raises(ValueError):
        initial_research_state("   ")


def test_graph_runs_expected_nodes():
    """工作流必须按计划、检索、回答的顺序执行。"""

    graph = build_research_graph()

    result = graph.invoke(
        initial_research_state(
            "Compare document 31 and document 32 for deepfake detection"
        )
    )

    assert [
        step["step"]
        for step in result["steps"]
    ] == [
        "plan",
        "retrieve",
        "classify_fields",
        "matrix",
        "evidence_judge",
        "final_matrix",
        "answer",
    ]


def test_graph_reports_insufficient_evidence():
    """没有实际证据时不得生成虚构结论。"""

    graph = build_research_graph()

    result = graph.invoke(
        initial_research_state(
            "Compare two papers"
        )
    )

    assert result["status"] == "insufficient_evidence"
    assert result["answer"] == "未找到充分证据"
    assert result["evidence"] == []


def test_graph_runs_are_independent():
    """两次研究请求不能共享执行状态。"""

    graph = build_research_graph()

    first = graph.invoke(
        initial_research_state(
            "Compare document 31 and document 32 for deepfake detection"
        )
    )

    second = graph.invoke(
        initial_research_state(
            "Compare document 41 and document 42 for graph fraud detection"
        )
    )

    assert first["question"] == (
        "Compare document 31 and document 32 for deepfake detection"
    )

    assert second["question"] == (
        "Compare document 41 and document 42 for graph fraud detection"
    )

    expected_steps = [
        "plan",
        "retrieve",
        "classify_fields",
        "matrix",
        "evidence_judge",
        "final_matrix",
        "answer",
    ]

    assert [
        step["step"] for step in first["steps"]
    ] == expected_steps

    assert [
        step["step"] for step in second["steps"]
    ] == expected_steps

    # 两次请求各自生成独立的证据矩阵。
    assert {
        row["document_id"]
        for row in first["evidence_matrix"]
    } == {31, 32}

    assert {
        row["document_id"]
        for row in second["evidence_matrix"]
    } == {41, 42}

    # 没有注入 Tool Executor，不应实际执行数据库检索。
    assert first["tool_calls"] == 0
    assert second["tool_calls"] == 0
    
def test_graph_skips_retrieval_when_planning_fails():
    """检索规划失败时，不应进入检索节点。"""

    graph = build_research_graph()

    result = graph.invoke(
        initial_research_state(
            "Compare two unknown papers"
        )
    )

    assert result["status"] == "insufficient_evidence"

    assert [
        item["step"]
        for item in result["steps"]
    ] == [
        "plan",
        "answer",
    ]

    assert result["steps"][0]["status"] == "failed"