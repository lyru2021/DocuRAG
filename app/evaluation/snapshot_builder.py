"""从真实论文正文构建可校验、独立保存的分块实验快照。"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.schemas import ChunkExperimentConfig
from app.models.document import Document, DocumentPage
from app.services.page_mapper import find_chunk_page_range
from app.services.text_chunker import split_text


class SnapshotBuilder:
    """复用生产分块算法生成实验快照。"""

    def __init__(self, db: Session):
        self.db = db

    def build(self, config: ChunkExperimentConfig) -> dict:
        """读取真实论文，保存分块参数、字符偏移和来源哈希。"""

        papers = []
        total_chunks = 0

        for document_id in config.document_ids:
            document = self.db.get(Document, document_id)

            if document is None:
                raise ValueError(
                    f"Document not found: {document_id}"
                )

            if (
                document.parse_status != "parsed"
                or not document.extracted_text
            ):
                raise ValueError(
                    f"Document not parsed: {document_id}"
                )

            pages = list(
                self.db.scalars(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == document_id)
                    .order_by(DocumentPage.page_number)
                ).all()
            )

            if not pages:
                raise ValueError(
                    f"Document has no page mappings: {document_id}"
                )

            text = document.extracted_text
            parts = split_text(
                text,
                chunk_size=config.chunk_size,
                overlap=config.overlap,
            )

            chunks = []

            for part in parts:
                # 防止分块内容与原文区间不一致。
                assert (
                    text[part.start_char:part.end_char]
                    == part.content
                )

                page_start, page_end = find_chunk_page_range(
                    part.start_char,
                    part.end_char,
                    pages,
                )

                if page_start is None:
                    raise ValueError(
                        f"Chunk has no page: {document_id}/"
                        f"{part.chunk_index}"
                    )

                chunks.append({
                    "chunk_index": part.chunk_index,
                    "start_char": part.start_char,
                    "end_char": part.end_char,
                    "page_start": page_start,
                    "page_end": page_end,
                    "content": part.content,
                })

            papers.append({
                "document_id": document.id,
                "title": document.title,
                "text_sha256": hashlib.sha256(
                    text.encode("utf-8")
                ).hexdigest(),
                "text_length": len(text),
                "page_count": len(pages),
                "chunk_count": len(chunks),
                "chunks": chunks,
            })

            total_chunks += len(chunks)

        return {
            "schema_version": 1,
            "experiment_id": config.experiment_id,
            "chunk_size": config.chunk_size,
            "overlap": config.overlap,
            "splitter": "app.services.text_chunker.split_text",
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "document_ids": config.document_ids,
            "total_chunks": total_chunks,
            "papers": papers,
        }

    @staticmethod
    def save(snapshot: dict, path: Path) -> None:
        """以原子替换方式保存 JSON 快照。"""

        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_name(path.name + ".tmp")

        try:
            temp_path.write_text(
                json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)