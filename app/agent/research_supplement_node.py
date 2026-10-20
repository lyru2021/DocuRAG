"""执行最多一轮补充检索，并保留已有的真实数据库证据。"""

from app.agent.evidence import collect_evidence
from app.agent.research_state import ResearchState
from app.agent.tool_executor import ToolExecutor
from app.agent.tool_schemas import ToolCall


def make_supplement_node(executor: ToolExecutor):
    """构造与初次检索共享执行预算的补检节点。"""

    def supplement_node(state: ResearchState) -> dict:
        """补检缺失字段并合并候选 Chunk。"""

        if state["supplementary_searches"] >= 1:
            return {
                "supplementary_tasks": [],
                "steps": state["steps"] + [
                    {
                        "step": "supplement",
                        "status": "skipped",
                        "detail": "Supplementary round limit reached",
                    }
                ],
            }

        # 原始证据不能因为补检失败而丢失。
        combined = list(state["evidence"])
        results = []
        records = []

        for task in state["supplementary_tasks"]:
            # 预算耗尽后不再尝试调用 Executor。
            if executor.call_count >= executor.max_calls:
                records.append({
                    "step": f"supplement:{task['task_id']}",
                    "status": "skipped",
                    "detail": "Shared tool budget exhausted",
                })
                break

            call = ToolCall(
                call_id=f"supplement_{task['task_id']}",
                name=task["tool_name"],
                arguments=task["arguments"],
            )

            result = executor.execute(call)
            results.append(result)

            records.append({
                "step": f"supplement:{task['task_id']}",
                "status": (
                    "success"
                    if result.status == "success"
                    else "failed"
                ),
                "detail": (
                    f"{task['purpose']}: {result.status}"
                ),
            })

        supplementary_evidence = collect_evidence(
            results,
            max_evidence=10,
        )

        # 只记录本轮新增的 Chunk，供二次事实提取使用。
        new_evidence = []
        seen = {
            (item["document_id"], item["chunk_id"])
            for item in combined
        }

        for item in supplementary_evidence:
            key = (item.document_id, item.chunk_id)

            if key in seen:
                continue

            seen.add(key)

            serialized = item.model_dump(mode="json")

            combined.append(serialized)
            new_evidence.append(serialized)

        return {
            "evidence": combined,
            "tool_calls": executor.call_count,
            "supplementary_searches": (
                state["supplementary_searches"] + 1
            ),
            "supplementary_tasks": [],
            "supplementary_new_evidence": new_evidence,
            "status": "supplementary_retrieval_completed",
            "steps": state["steps"] + records + [
                {
                    "step": "supplement",
                    "status": "success",
                    "detail": (
                        f"Total evidence chunks: {len(combined)}"
                    ),
                }
            ],
        }

    return supplement_node