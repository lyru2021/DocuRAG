"""验证跨论文检索规划、文档识别及安全约束。"""

import pytest

from app.agent.research_planner import (
    ResearchPlanningError,
    build_retrieval_plan,
    extract_document_ids,
)



def test_extracts_english_document_ids():
    """识别英文文档标识。"""

    ids = extract_document_ids(
        "Compare Document 31 and Document ID=32"
    )

    assert ids == [31, 32]


def test_extracts_chinese_document_ids():
    """识别中文论文标识。"""

    ids = extract_document_ids(
        "比较论文31和论文32的深度伪造检测方法"
    )

    assert ids == [31, 32]


def test_deduplicates_document_ids():
    """相同论文不得生成重复任务。"""

    ids = extract_document_ids(
        "Compare document 31, document 32, and document 31"
    )

    assert ids == [31, 32]


def test_planner_creates_two_independent_tasks():
    """两篇论文必须得到两个独立检索任务。"""

    tasks = build_retrieval_plan(
        "Compare document 31 and document 32 "
        "for deepfake detection"
    )

    assert len(tasks) == 2

    assert [task["task_id"] for task in tasks] == [
        "T1",
        "T2",
    ]

    assert [
        task["arguments"]["document_id"]
        for task in tasks
    ] == [31, 32]

    assert all(
        task["tool_name"] == "search_chunks"
        for task in tasks
    )


def test_planner_rejects_single_document():
    """只有一个文档 ID 时不能声称完成跨论文比较。"""

    with pytest.raises(ResearchPlanningError):
        build_retrieval_plan(
            "Compare deepfake detection in document 31"
        )


def test_planner_rejects_excessive_documents():
    """过多文档不能绕过检索规模限制。"""

    with pytest.raises(
        ResearchPlanningError,
        match="Too many",
    ):
        build_retrieval_plan(
            "Compare document 31, document 32, "
            "document 33 and document 34 "
            "for deepfake detection"
        )


def test_planner_does_not_treat_year_as_document_id():
    """年份不能被误认为论文数据库 ID。"""

    ids = extract_document_ids(
        "Compare research published in 2025 and 2026"
    )

    assert ids == []

def test_planner_accepts_detection_comparison_question():
    """检测方法比较问题应优先检索研究方法。"""

    question = (
        "Compare the detection methods used "
        "in document 31 and document 32."
    )

    plan = build_retrieval_plan(question)

    assert len(plan) == 2

    assert [
        task["arguments"]["document_id"]
        for task in plan
    ] == [31, 32]

    assert all(
        task["arguments"]["query"] == "model"
        for task in plan
    )



@pytest.mark.parametrize(
    ("question", "expected_query"),
    [
        (
            "Compare the detection methods used "
            "in document 31 and document 32.",
            "model",
        ),
        (
            "Compare the datasets and experimental conditions "
            "in document 31 and document 32.",
            "dataset",
        ),
        (
            "Compare the evaluation metrics reported "
            "in document 31 and document 32.",
            "evaluation",
        ),
        (
            "Compare the main experimental findings "
            "in document 31 and document 32.",
            "results",
        ),
        (
            "Compare the similarities and differences in "
            "deepfake detection between document 31 and document 32.",
            "detection",
        ),
    ],
)
def test_planner_handles_five_research_questions(
    question,
    expected_query,
):
    """五类跨论文问题必须正确识别目标与检索意图。"""

    plan = build_retrieval_plan(question)

    assert len(plan) == 2

    assert [
        task["arguments"]["document_id"]
        for task in plan
    ] == [31, 32]

    assert all(
        task["arguments"]["query"] == expected_query
        for task in plan
    )