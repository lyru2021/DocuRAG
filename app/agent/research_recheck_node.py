"""处理补检新增证据，并重新计算跨论文引文覆盖情况。"""

from app.agent.evidence_judge import judge_evidence_coverage
from app.agent.fact_extractor import FactExtractor
from app.agent.research_state import ResearchState


def make_supplementary_fact_node(
    extractor: FactExtractor | None,
):
    """构建只处理补检新增 Chunk 的事实提取节点。"""

    def supplementary_fact_node(state: ResearchState) -> dict:
        """保留既有核验记录，并追加新证据的核验结果。"""

        new_evidence = state["supplementary_new_evidence"]

        if extractor is None or not new_evidence:
            return {
                "steps": state["steps"] + [
                    {
                        "step": "supplementary_facts",
                        "status": "skipped",
                        "detail": (
                            "No extractor or no new evidence"
                        ),
                    }
                ],
            }

        try:
            result = extractor.extract(
                question=state["question"],
                evidence=new_evidence,
            )

        except Exception as exc:
            # 模型失败不应清空初检时已经验证的事实。
            return {
                "steps": state["steps"] + [
                    {
                        "step": "supplementary_facts",
                        "status": "failed",
                        "detail": type(exc).__name__,
                    }
                ],
            }

        existing = list(state["fact_verifications"])

        additions = [
            item.model_dump(mode="json")
            for item in result.verifications
        ]

        # 按事实内容与来源去重，保留不同核验状态的记录。
        seen = {
            (
                item["fact"]["document_id"],
                item["fact"]["chunk_id"],
                item["fact"]["field"],
                item["fact"]["quote"],
                item["fact"]["claim"],
                item["status"],
            )
            for item in existing
        }

        for item in additions:
            key = (
                item["fact"]["document_id"],
                item["fact"]["chunk_id"],
                item["fact"]["field"],
                item["fact"]["quote"],
                item["fact"]["claim"],
                item["status"],
            )

            if key not in seen:
                seen.add(key)
                existing.append(item)

        usage = dict(state["extraction_usage"])

        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "latency_ms",
        ):
            usage[key] = usage.get(key, 0) + getattr(
                result, key
            )

        return {
            "fact_verifications": existing,
            "extraction_usage": usage,
            "steps": state["steps"] + [
                {
                    "step": "supplementary_facts",
                    "status": "success",
                    "detail": (
                        f"Processed {len(new_evidence)} new chunks; "
                        f"received {len(additions)} verifications"
                    ),
                }
            ],
        }

    return supplementary_fact_node


def evidence_recheck_node(state: ResearchState) -> dict:
    """重新计算证据覆盖度，不生成第二轮补检任务。"""

    judgement = judge_evidence_coverage(state)

    return {
        "evidence_judgement": judgement.model_dump(
            mode="json"
        ),
        "supplementary_tasks": [],
        "status": "evidence_rechecked",
        "steps": state["steps"] + [
            {
                "step": "evidence_recheck",
                "status": "success",
                "detail": (
                    "Final quote coverage sufficient: "
                    f"{judgement.sufficient_quote_coverage}"
                ),
            }
        ],
    }