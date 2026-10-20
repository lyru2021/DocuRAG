"""使用真实 PostgreSQL 和 DeepSeek 验收 Day 12 跨论文科研工作流。"""

import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# 必须在导入数据库 SessionLocal 等模块前加载环境变量。
load_dotenv()

from sqlalchemy import select

from app.agent.fact_extractor import FactExtractor
from app.agent.openai_adapter import OpenAIAdapter
from app.agent.paper_tools import build_paper_tool_registry
from app.agent.research_graph import (
    build_research_graph,
    initial_research_state,
)
from app.agent.research_report import render_research_report
from app.agent.tool_db import make_production_tool_session
from app.agent.tool_executor import ToolExecutor
from app.db.session import SessionLocal
from app.models.document import Document


QUESTIONS = [
    "Compare the detection methods used in document 31 and document 32.",
    "Compare the datasets and experimental conditions in document 31 and document 32.",
    "Compare the evaluation metrics reported in document 31 and document 32.",
    "Compare the main experimental findings in document 31 and document 32.",
    "Compare the similarities and differences in deepfake detection between document 31 and document 32.",
]


def check_documents():
    """执行只读预检，确认两篇目标论文存在且已解析。"""

    with SessionLocal() as db:
        rows = db.execute(
            select(
                Document.id,
                Document.title,
                Document.parse_status,
            ).where(
                Document.id.in_([31, 32])
            )
        ).all()

    documents = {
        row.id: {
            "title": row.title,
            "parse_status": row.parse_status,
        }
        for row in rows
    }

    for document_id in (31, 32):
        info = documents.get(document_id)

        if info is None:
            raise RuntimeError(
                f"Document {document_id} does not exist"
            )

        if info["parse_status"] != "parsed":
            raise RuntimeError(
                f"Document {document_id} is not parsed"
            )

    return documents


def make_graph():
    """为每道题创建独立的真实工具预算及 DeepSeek 提取器。"""

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    model = os.getenv("LLM_MODEL") or "deepseek-flash"

    llm = OpenAIAdapter(
        model=model,
        api_key=api_key,
        base_url="https://api.deepseek.com",
        provider="deepseek",
        timeout=60.0,
    )

    registry = build_paper_tool_registry(
        make_production_tool_session(
            statement_timeout_ms=3000
        )
    )

    executor = ToolExecutor(
        registry,
        max_calls=5,
        max_output_chars=10000,
    )

    extractor = FactExtractor(
        llm,
        max_facts=10,
        max_evidence=10,
        max_content_chars=1500,
    )

    return build_research_graph(
        executor=executor,
        fact_extractor=extractor,
        enable_supplement=True,
    )


def make_audit_rows(question_id, matrix):
    """为每条已核验引文生成独立人工审核记录。"""

    rows = []

    for paper in matrix:
        for fact in paper.get("quote_verified_facts", []):
            rows.append({
                "question_id": question_id,
                "document_id": fact["document_id"],
                "chunk_id": fact["chunk_id"],
                "page_start": fact["page_start"],
                "page_end": fact["page_end"],
                "field": fact["field"],
                "claim": fact["claim"],
                "quote": fact["quote"],
                "quote_status": fact["verification_status"],
                "human_semantic_support": "",
                "human_notes": "",
            })

    return rows


def evaluate_one(question_id, question, output_dir):
    """运行一道真实问题并持久化全部可审计结果。"""

    print(f"\n[Q{question_id}] {question}", flush=True)

    graph = make_graph()

    result = graph.invoke(
        initial_research_state(question)
    )

    matrix = result["evidence_matrix"]
    verifications = result["fact_verifications"]
    usage = result.get("extraction_usage", {})

    verified_count = sum(
        item.get("status") == "quote_verified"
        for item in verifications
    )

    rejected_count = sum(
        item.get("status") != "quote_verified"
        for item in verifications
    )

    summary = {
        "question_id": question_id,
        "question": question,
        "status": result["status"],
        "answer": result.get("answer"),
        "tool_calls": result["tool_calls"],
        "supplementary_searches": result["supplementary_searches"],
        "retrieved_chunks": len(result["evidence"]),
        "supplementary_new_chunks": len(
            result.get("supplementary_new_evidence", [])
        ),
        "verified_quotes": verified_count,
        "rejected_quotes": rejected_count,
        "final_matrix_facts": sum(
            len(paper.get("quote_verified_facts", []))
            for paper in matrix
        ),
        "extraction_usage": usage,
        "evidence_judgement": result.get(
            "evidence_judgement", {}
        ),
        "steps": result["steps"],
    }

    if result["tool_calls"] > 5:
        raise RuntimeError("Tool budget exceeded")

    if result["supplementary_searches"] > 1:
        raise RuntimeError("Supplementary round limit exceeded")

    # 保存完整运行状态，包含原文证据。
    state_path = output_dir / f"Q{question_id}_state.json"
    state_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_path = output_dir / f"Q{question_id}_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = render_research_report(question, matrix)

    (output_dir / f"Q{question_id}_report.md").write_text(
        report,
        encoding="utf-8",
    )

    print(
        f"  Tools: {summary['tool_calls']}/5"
        f" | Supplement rounds: {summary['supplementary_searches']}"
        f" | Verified quotes: {verified_count}"
        f" | Rejected quotes: {rejected_count}"
        f" | Tokens: {usage.get('total_tokens', 0)}",
        flush=True,
    )

    return summary, make_audit_rows(question_id, matrix)


def save_audit_csv(rows, output_dir):
    """导出需要人工判断语义支持关系的审核表。"""

    fieldnames = [
        "question_id",
        "document_id",
        "chunk_id",
        "page_start",
        "page_end",
        "field",
        "claim",
        "quote",
        "quote_status",
        "human_semantic_support",
        "human_notes",
    ]

    with (output_dir / "human_audit.csv").open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    """提供单题试运行和五题完整验收两种模式。"""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all five research questions",
    )
    parser.add_argument(
        "--question",
        type=int,
        choices=range(1, 6),
        default=1,
        help="Question number for single-question mode",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    output_dir = args.output_dir or (
        Path("evaluation/results")
        / f"day12_real_{datetime.now():%Y%m%d_%H%M%S}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    documents = check_documents()

    print("PostgreSQL papers:", documents)
    print(
        "DeepSeek model:",
        os.getenv("LLM_MODEL") or "deepseek-flash",
    )
    print("Output directory:", output_dir)

    selected = (
        list(enumerate(QUESTIONS, start=1))
        if args.all
        else [(args.question, QUESTIONS[args.question - 1])]
    )

    summaries = []
    audit_rows = []
    failures = []

    for question_id, question in selected:
        try:
            summary, rows = evaluate_one(
                question_id,
                question,
                output_dir,
            )
            summaries.append(summary)
            audit_rows.extend(rows)

        except Exception as exc:
            # 单题失败后保留之前成功完成的结果。
            # 不打印异常对象，避免泄露凭据或请求内容。
            failures.append({
                "question_id": question_id,
                "error_type": type(exc).__name__,
            })
            print(
                f"[Q{question_id}] FAILED: {type(exc).__name__}",
                flush=True,
            )

        finally:
            # 每完成一道题都保存当前结果。
            (output_dir / "overview.json").write_text(
                json.dumps(
                    {
                        "documents": documents,
                        "summaries": summaries,
                        "failures": failures,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            save_audit_csv(audit_rows, output_dir)

    print("\nFinished")
    print("Completed:", len(summaries))
    print("Failed:", len(failures))
    print("Output:", output_dir)

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()