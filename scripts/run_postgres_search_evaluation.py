"""比较两种切分配置下三种真实 PostgreSQL 检索策略。"""

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.evaluation.metrics import (
    RankedChunk,
    aggregate_metrics,
    evaluate_question,
)
from app.evaluation.postgres_fusion import fuse_experiment_hits
from app.evaluation.postgres_retriever import ExperimentPostgresRetriever
from app.evaluation.schemas import EvaluationQuestion


ROOT = Path("evaluation")
OUTPUT = ROOT / "results"
QUESTIONS_PATH = ROOT / "questions/audio_deepfake_15.json"

EXPERIMENTS = (
    "chunk300_overlap50",
    "chunk500_overlap50",
)
STRATEGIES = ("literal", "fts", "hybrid")


def load_json(path: Path):
    """读取 JSON，并记录文件哈希以确保实验可追溯。"""

    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def verify_inputs(snapshots: dict, questions: list) -> None:
    """验证两套快照和标注使用同一批原文与文档。"""

    first = snapshots[EXPERIMENTS[0]]
    second = snapshots[EXPERIMENTS[1]]

    if first["document_ids"] != second["document_ids"]:
        raise ValueError("Snapshot document sets differ")

    if set(first["document_ids"]) != {31, 32}:
        raise ValueError("Unexpected document IDs")

    for snapshot in (first, second):
        papers = {
            paper["document_id"]: paper
            for paper in snapshot["papers"]
        }

        if set(papers) != {31, 32}:
            raise ValueError("Unexpected snapshot papers")

        if sum(
            paper["chunk_count"]
            for paper in snapshot["papers"]
        ) != snapshot["total_chunks"]:
            raise ValueError("Snapshot chunk count mismatch")

    papers_a = {
        paper["document_id"]: paper
        for paper in first["papers"]
    }
    papers_b = {
        paper["document_id"]: paper
        for paper in second["papers"]
    }

    for document_id in (31, 32):
        if (
            papers_a[document_id]["text_sha256"]
            != papers_b[document_id]["text_sha256"]
        ):
            raise ValueError("Source text hashes differ")

    if len(questions) < 15:
        raise ValueError("At least 15 questions are required")

    if len({q.question_id for q in questions}) != len(questions):
        raise ValueError("Duplicate question IDs")

    for question in questions:
        for evidence in question.evidence:
            paper = papers_a.get(evidence.document_id)
            if paper is None:
                raise ValueError("Evidence document missing")

            if evidence.end_char > paper["text_length"]:
                raise ValueError("Evidence offset exceeds source text")


def retrieve(
    retriever,
    experiment_id: str,
    query: str,
    strategy: str,
    document_ids: list[int],
):
    """执行指定策略，并返回真实 PostgreSQL 候选。"""

    kwargs = {
        "experiment_id": experiment_id,
        "query": query,
        "document_ids": document_ids,
        "limit": 5,
    }

    if strategy != "hybrid":
        return retriever.search(
            **kwargs,
            mode=strategy,
        )

    literal_hits = retriever.search(
        **kwargs,
        mode="literal",
    )

    fts_hits = retriever.search(
        **kwargs,
        mode="fts",
    )

    return fuse_experiment_hits(
        literal_hits,
        fts_hits,
        limit=5,
    )


def run_group(
    retriever,
    experiment_id: str,
    strategy: str,
    questions: list[EvaluationQuestion],
    document_ids: list[int],
):
    """计算一组真实检索结果及逐题执行耗时。"""

    records = []
    latencies = []

    for question in questions:
        start_ns = perf_counter_ns()

        hits = retrieve(
            retriever,
            experiment_id,
            question.query,
            strategy,
            document_ids,
        )

        elapsed_ms = (
            perf_counter_ns() - start_ns
        ) / 1_000_000

        ranked = [
            RankedChunk(
                document_id=hit.document_id,
                chunk_index=hit.chunk_index,
                start_char=hit.start_char,
                end_char=hit.end_char,
            )
            for hit in hits
        ]

        metrics = evaluate_question(
            question,
            ranked,
            k=5,
        )

        latencies.append(elapsed_ms)

        records.append({
            **metrics,
            "query": question.query,
            "latency_ms": elapsed_ms,
            "retrieved_chunks": [
                {
                    "document_id": hit.document_id,
                    "chunk_index": hit.chunk_index,
                    "start_char": hit.start_char,
                    "end_char": hit.end_char,
                    "retrieval_source": hit.retrieval_source,
                }
                for hit in hits
            ],
        })

    summary = aggregate_metrics(records)

    summary.update({
        "mean_latency_ms": sum(latencies) / len(latencies),
        "min_latency_ms": min(latencies),
        "max_latency_ms": max(latencies),
    })

    return {
        "summary": summary,
        "questions": records,
    }


def main() -> None:
    """运行全部检索组合并保存逐题证据和指标。"""

    OUTPUT.mkdir(parents=True, exist_ok=True)

    question_data, question_hash = load_json(
        QUESTIONS_PATH
    )

    questions = [
        EvaluationQuestion.model_validate(item)
        for item in question_data
    ]

    snapshots = {}
    snapshot_hashes = {}

    for experiment_id in EXPERIMENTS:
        path = ROOT / "snapshots" / f"{experiment_id}.json"
        snapshots[experiment_id], snapshot_hashes[
            experiment_id
        ] = load_json(path)

    verify_inputs(snapshots, questions)

    engine = create_engine(
        get_settings().DATABASE_URL,
        pool_pre_ping=True,
    )

    try:
        if engine.url.database != "docurag_dev":
            raise RuntimeError(
                "Evaluation must use docurag_dev"
            )

        with Session(engine) as db:
            retriever = ExperimentPostgresRetriever(db)

            for experiment_id in EXPERIMENTS:
                snapshot = snapshots[experiment_id]

                for strategy in STRATEGIES:
                    path = OUTPUT / (
                        f"{experiment_id}_{strategy}_postgres.json"
                    )

                    # 已有实验结果保留原样，避免重复运行时覆盖历史数据。
                    if path.exists():
                        print(f"SKIPPED (already exists): {path}")
                        continue
                    result = run_group(
                        retriever,
                        experiment_id,
                        strategy,
                        questions,
                        snapshot["document_ids"],
                    )

                    output_data = {
                        "experiment_id": experiment_id,
                        "strategy": strategy,
                        "top_k": 5,
                        "chunk_size": snapshot["chunk_size"],
                        "overlap": snapshot["overlap"],
                        "total_chunks": snapshot["total_chunks"],
                        "document_ids": snapshot["document_ids"],
                        "snapshot_sha256": snapshot_hashes[
                            experiment_id
                        ],
                        "questions_sha256": question_hash,
                        "executed_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "environment": {
                            "database": engine.url.database,
                            "python_version": sys.version,
                            "platform": platform.platform(),
                        },
                        "timing_scope": (
                            "PostgreSQL retrieval calls and "
                            "Python fusion; excludes file I/O"
                        ),
                        **result,
                    }


                    path.write_text(
                        json.dumps(
                            output_data,
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )

                    print(f"\n{experiment_id} / {strategy}")
                    print(
                        json.dumps(
                            result["summary"],
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                    print("Saved:", path)

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()