"""验证独立数据库事务无法为同一文档创建多个活跃任务。"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.document import Document
from app.models.processing_job import ProcessingJob


def test_unique_active_job_across_sessions():
    """两个独立 Session 不能提交同一文档的两条活跃任务。"""

    # 独立数据库测试会真实提交数据，必须连接隔离的测试库。
    assert engine.url.database == "docurag_test"

    document_id = None

    try:
        with Session(engine) as db:
            document = Document(
                title="Concurrent retry test",
                filename="concurrent-test.pdf",
                media_type="application/pdf",
                file_size=1,
                content_hash="test-hash",
                parse_status="pending",
                text_length=0,
            )
            db.add(document)
            db.flush()
            document_id = document.id
            db.commit()

        with Session(engine) as first:
            first.add(
                ProcessingJob(
                    document_id=document_id,
                    status="pending",
                )
            )
            first.commit()

        with Session(engine) as second:
            second.add(
                ProcessingJob(
                    document_id=document_id,
                    status="processing",
                )
            )

            with pytest.raises(IntegrityError):
                second.commit()

            second.rollback()

            # 回滚后 Session 仍然可查询数据库。
            active_count = second.scalar(
                select(func.count())
                .select_from(ProcessingJob)
                .where(
                    ProcessingJob.document_id == document_id,
                    ProcessingJob.status.in_(
                        ["pending", "processing"]
                    ),
                )
            )

            assert active_count == 1

    finally:
        if document_id is not None:
            with Session(engine) as db:
                document = db.get(Document, document_id)

                if document is not None:
                    db.delete(document)
                    db.commit()