"""验证两个独立 PostgreSQL 事务对同一文档的行锁竞争。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.document import Document


def test_document_row_lock_blocks_second_transaction():
    """第二个事务必须等待第一个事务释放文档行锁。"""

    assert engine.url.database == "docurag_test"

    with Session(engine) as db:
        document = Document(
            title="Document lock test",
            filename="lock-test.pdf",
            media_type="application/pdf",
            file_size=1,
            content_hash="lock-test-hash",
            parse_status="pending",
            text_length=0,
        )
        db.add(document)
        db.commit()
        document_id = document.id

    first_locked = Event()
    release_first = Event()
    second_finished = Event()

    def first_transaction():
        with Session(engine) as db:
            db.execute(
                select(Document)
                .where(Document.id == document_id)
                .with_for_update()
            ).scalar_one()

            first_locked.set()

            if not release_first.wait(timeout=5):
                raise TimeoutError("First transaction release timeout")

            db.commit()

    def second_transaction():
        if not first_locked.wait(timeout=5):
            raise TimeoutError("First transaction did not lock")

        with Session(engine) as db:
            db.execute(text("SET LOCAL lock_timeout = '3s'"))

            db.execute(
                select(Document)
                .where(Document.id == document_id)
                .with_for_update()
            ).scalar_one()

            second_finished.set()
            db.commit()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(first_transaction)
            second_future = executor.submit(second_transaction)

            assert first_locked.wait(timeout=5)

            # 事务 A 持有锁时，事务 B 尚不应完成。
            assert not second_finished.wait(timeout=0.2)

            release_first.set()

            first_future.result(timeout=5)
            second_future.result(timeout=5)

            assert second_finished.is_set()

    finally:
        release_first.set()

        with Session(engine) as db:
            document = db.get(Document, document_id)
            if document is not None:
                db.delete(document)
                db.commit()
