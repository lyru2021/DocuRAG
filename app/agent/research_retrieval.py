"""执行跨论文检索计划，并整理工具状态及候选证据。"""

from app.agent.evidence import collect_evidence
from app.agent.research_state import ResearchState
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_schemas import ToolCall


def make_retrieve_node(executor: ToolExecutor):
    """创建使用共享工具预算的 LangGraph 检索节点。"""

    def retrieve_node(state: ResearchState) -> dict:
        """按计划依次执行任务，合并有效证据。"""

        results = []
        records = []

        for task in state["retrieval_plan"]:
            call = ToolCall(
                call_id=f"research_{task['task_id']}",
                name=task["tool_name"],
                arguments=task["arguments"],
            )

            result = executor.execute(call)
            results.append(result)

            records.append({
                "step": f"retrieve:{task['task_id']}",
                "status": (
                    "success"
                    if result.status == "success"
                    else "failed"
                ),
                "detail": (
                    f"{task['tool_name']}: {result.status}"
                ),
            })

            # 达到预算上限时停止后续任务。
            if result.status == "limit_exceeded":
                break

        evidence = collect_evidence(
            results,
            max_evidence=10,
        )

        return {
            "tool_calls": executor.call_count,
            "evidence": [
                item.model_dump(mode="json")
                for item in evidence
            ],
            "status": "retrieval_completed",
            "steps": state["steps"] + records,
        }

    return retrieve_node