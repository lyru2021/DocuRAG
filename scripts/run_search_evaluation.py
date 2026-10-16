"""运行两套独立 Chunk 快照的证据检索评估并保存结果。"""

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns

from app.evaluation.literal_retriever import search_snapshot
from app.evaluation.metrics import aggregate_metrics, evaluate_question
from app.evaluation.schemas import EvaluationQuestion


SNAPSHOT_DIR = Path("evaluation/snapshots")
QUESTION_FILE = Path("evaluation/questions/audio_deepfake_15.json")
OUTPUT_DIR = Path("evaluation/results")


def load_json(path: Path) -> tuple[object, str]:
    """加载 JSON 并计算文件内容 SHA-256。"""

    raw = path.read_bytes()
    return (
        json.loads(raw),
        hashlib.sha256(raw).hexdigest(),
    )


def run_experiment(
    snapshot: dict,
    questions: list[EvaluationQuestion],
) -> dict:
    """执行一组固定快照上的 Top-5 检索评估。"""

    results = []
    latencies_ms = []

    for question in questions:
        start_ns = perf_counter_ns()

        ranked = search_snapshot(
            snapshot,
            question.query,
            limit=5,
        )

        elapsed_ms = (
            perf_counter_ns() - start_ns
        ) / 1_000_000

        metrics = evaluate_question(
            question,
            ranked,
            k=5,
        )

        latencies_ms.append(elapsed_ms)

        results.append({
            **metrics,
            "query": question.query,
            "latency_ms": elapsed_ms,
            "retrieved_chunks": [
                {
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                }
                for chunk in ranked
            ],
        })

    summary = aggregate_metrics(results)

    summary["mean_latency_ms"] = (
        sum(latencies_ms) / len(latencies_ms)
    )

    summary["max_latency_ms"] = max(latencies_ms)
    summary["min_latency_ms"] = min(latencies_ms)

    return {
        "summary": summary,
        "questions": results,
    }


def main() -> None:
    """运行两组实验并保存各自的完整评估记录。"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    question_data, question_hash = load_json(
        QUESTION_FILE
    )

    questions = [
        EvaluationQuestion.model_validate(item)
        for item in question_data
    ]

    if len(questions) < 15:
        raise ValueError(
            "Evaluation requires at least 15 questions"
        )

    for experiment_id in (
        "chunk300_overlap50",
        "chunk500_overlap50",
    ):
        path = SNAPSHOT_DIR / f"{experiment_id}.json"
        snapshot, snapshot_hash = load_json(path)

        if snapshot["experiment_id"] != experiment_id:
            raise ValueError("Snapshot identity mismatch")

        if snapshot["total_chunks"] != sum(
            len(paper["chunks"])
            for paper in snapshot["papers"]
        ):
            raise ValueError("Snapshot chunk count mismatch")

        document_ids = set(snapshot["document_ids"])

        for question in questions:
            for evidence in question.evidence:
                if evidence.document_id not in document_ids:
                    raise ValueError(
                        f"Evidence document missing: "
                        f"{evidence.document_id}"
                    )

        evaluation = run_experiment(
            snapshot,
            questions,
        )

        output = {
            "experiment_id": experiment_id,
            "retrieval_method": "snapshot_literal",
            "top_k": 5,
            "snapshot_sha256": snapshot_hash,
            "questions_sha256": question_hash,
            "document_ids": snapshot["document_ids"],
            "chunk_size": snapshot["chunk_size"],
            "overlap": snapshot["overlap"],
            "total_chunks": snapshot["total_chunks"],
            "executed_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "environment": {
                "python_version": sys.version,
                "platform": platform.platform(),
                "processor": platform.processor(),
            },
            **evaluation,
        }

        output_path = (
            OUTPUT_DIR / f"{experiment_id}_literal.json"
        )

        output_path.write_text(
            json.dumps(
                output,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\nExperiment: {experiment_id}")
        print(f"Chunks: {snapshot['total_chunks']}")
        print(
            json.dumps(
                output["summary"],
                ensure_ascii=False,
                indent=2,
            )
        )
        print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()