"""构建科研 Agent 的最小 LangGraph 状态工作流。"""

from langgraph.graph import END, START, StateGraph

from app.agent.research_state import ResearchState
from app.agent.research_planner import (
    ResearchPlanningError,
    build_retrieval_plan,
)
from app.agent.research_retrieval import make_retrieve_node
from app.agent.tool_executor import ToolExecutor
from app.agent.evidence_matrix import build_evidence_matrix
from app.agent.research_planner import extract_document_ids
from app.agent.field_evidence import classify_evidence_fields
from app.agent.fact_extractor import FactExtractor
from app.agent.research_fact_node import make_fact_extraction_node
from app.agent.evidence_judge import judge_evidence_coverage
from app.agent.research_supplement import plan_supplementary_tasks
from app.agent.research_supplement_node import make_supplement_node
from app.agent.research_recheck_node import evidence_recheck_node, make_supplementary_fact_node
from app.agent.research_final_matrix import final_matrix_node

def plan_node(state: ResearchState) -> dict:
    """生成跨论文检索计划，并记录规划结果。"""

    try:
        plan = build_retrieval_plan(state["question"])

    except ResearchPlanningError as exc:
        return {
            "retrieval_plan": [],
            "status": "planning_failed",
            "steps": state["steps"] + [
                {
                    "step": "plan",
                    "status": "failed",
                    "detail": str(exc),
                }
            ],
        }

    return {
        "retrieval_plan": plan,
        "status": "planning_completed",
        "steps": state["steps"] + [
            {
                "step": "plan",
                "status": "success",
                "detail": f"Created {len(plan)} retrieval tasks",
            }
        ],
    }

def retrieve_node(state: ResearchState) -> dict:
    """预留检索节点，当前不访问数据库。"""

    return {
        "status": "retrieval_completed",
        "steps": state["steps"] + [
            {
                "step": "retrieve",
                "status": "skipped",
                "detail": "No retrieval tasks configured",
            }
        ],
    }


def answer_node(state: ResearchState) -> dict:
    """在缺少证据时明确返回不足，而不是编造结论。"""

    return {
        "answer": "未找到充分证据",
        "status": "insufficient_evidence",
        "steps": state["steps"] + [
            {
                "step": "answer",
                "status": "success",
                "detail": "Insufficient evidence reported",
            }
        ],
    }

def after_plan(state: ResearchState) -> str:
    """规划失败时跳过检索，进入安全回答节点。"""

    if state["status"] == "planning_failed":
        return "answer"

    return "retrieve"

def build_research_graph(
    executor: ToolExecutor | None = None,
    fact_extractor: FactExtractor | None = None,
    *,
    enable_supplement: bool = True,
):
    """构建包含检索、事实提取、补检与最终矩阵的科研工作流。"""

    graph = StateGraph(ResearchState)

    # 1. 注册基础节点。
    graph.add_node("plan", plan_node)

    if executor is None:
        graph.add_node("retrieve", retrieve_node)
    else:
        graph.add_node(
            "retrieve",
            make_retrieve_node(executor),
        )

    graph.add_node("classify_fields", classify_fields_node)
    graph.add_node("matrix", matrix_node)
    graph.add_node("evidence_judge", evidence_judge_node)
    graph.add_node("final_matrix", final_matrix_node)
    graph.add_node("answer", answer_node)

    # 2. 规划阶段。
    graph.add_edge(START, "plan")

    graph.add_conditional_edges(
        "plan",
        after_plan,
        {
            "retrieve": "retrieve",
            "answer": "answer",
        },
    )

    # 3. 初始检索和字段分类。
    graph.add_edge("retrieve", "classify_fields")

    if fact_extractor is None:
        graph.add_edge("classify_fields", "matrix")
    else:
        graph.add_node(
            "extract_facts",
            make_fact_extraction_node(fact_extractor),
        )

        graph.add_edge("classify_fields", "extract_facts")
        graph.add_edge("extract_facts", "matrix")

    # 4. 构建证据矩阵并进行首次覆盖度判断。
    graph.add_edge("matrix", "evidence_judge")

    # 5. 根据配置决定是否允许补充检索。
    if executor is not None and enable_supplement:
        graph.add_node(
            "supplement",
            make_supplement_node(executor),
        )

        graph.add_node(
            "supplementary_facts",
            make_supplementary_fact_node(fact_extractor),
        )

        graph.add_node(
            "evidence_recheck",
            evidence_recheck_node,
        )

        graph.add_conditional_edges(
            "evidence_judge",
            after_evidence_judge,
            {
                "supplement": "supplement",
                "answer": "final_matrix",
            },
        )

        # 补检后只处理新增 Chunk，再复核一次。
        graph.add_edge("supplement", "supplementary_facts")
        graph.add_edge("supplementary_facts", "evidence_recheck")
        graph.add_edge("evidence_recheck", "final_matrix")

    else:
        # 关闭补检时，直接生成最终矩阵。
        graph.add_edge("evidence_judge", "final_matrix")

    # 6. 两种运行模式共享统一出口。
    # 这两条边必须放在 if / else 外面。
    graph.add_edge("final_matrix", "answer")
    graph.add_edge("answer", END)

    return graph.compile()


def initial_research_state(question: str) -> ResearchState:
    """初始化单次请求状态，不复用上一轮数据。"""

    if not question.strip():
        raise ValueError("question must not be blank")

    return {
        "question": question,
        "retrieval_plan": [],
        "tool_calls": 0,
        "evidence": [],
        "evidence_matrix": [],
        "supplementary_searches": 0,
        "answer": None,
        "status": "pending",
        "steps": [],
        "field_candidates": {},
        "fact_verifications": [],
        "extraction_usage": {},
        "evidence_judgement": {},
        "supplementary_tasks": [],
        "supplementary_new_evidence": [],
    }

def matrix_node(state: ResearchState) -> dict:
    """按论文汇总候选证据，不自动断言研究结论。"""

    document_ids = extract_document_ids(
        state["question"]
    )

    matrix = build_evidence_matrix(
        document_ids=document_ids,
        evidence=state["evidence"],
    )

    return {
        "evidence_matrix": [
            row.model_dump(mode="json")
            for row in matrix
        ],
        "status": "matrix_completed",
        "steps": state["steps"] + [
            {
                "step": "matrix",
                "status": "success",
                "detail": (
                    f"Built {len(matrix)} evidence matrix rows"
                ),
            }
        ],
    }

def classify_fields_node(state: ResearchState) -> dict:
    """将已检索的真实 Chunk 分类为研究字段候选证据。"""

    candidates = classify_evidence_fields(
        state["evidence"],
        max_candidates_per_field=5,
    )

    serialized = {
        field: [
            item.model_dump(mode="json")
            for item in items
        ]
        for field, items in candidates.items()
    }

    counts = {
        field: len(items)
        for field, items in serialized.items()
    }

    return {
        "field_candidates": serialized,
        "status": "fields_classified",
        "steps": state["steps"] + [
            {
                "step": "classify_fields",
                "status": "success",
                "detail": (
                    "Field candidates classified: "
                    f"{counts}"
                ),
            }
        ],
    }

def evidence_judge_node(state: ResearchState) -> dict:
    """检查引文覆盖度并确定是否需要补检。"""

    judgement = judge_evidence_coverage(state)

    tasks = []

    if (
        not judgement.sufficient_quote_coverage
        and state["supplementary_searches"] < 1
    ):
        tasks = plan_supplementary_tasks(
            judgement.missing_fields,
            max_tasks=3,
        )

    return {
        "evidence_judgement": judgement.model_dump(mode="json"),
        "supplementary_tasks": tasks,
        "status": "evidence_checked",
        "steps": state["steps"] + [
            {
                "step": "evidence_judge",
                "status": "success",
                "detail": (
                    f"Quote coverage sufficient: "
                    f"{judgement.sufficient_quote_coverage}; "
                    f"supplementary tasks: {len(tasks)}"
                ),
            }
        ],
    }


def after_evidence_judge(state: ResearchState) -> str:
    """仅在存在补检任务且未超轮数时进入补检节点。"""

    if (
        state["supplementary_tasks"]
        and state["supplementary_searches"] < 1
    ):
        return "supplement"

    return "answer"