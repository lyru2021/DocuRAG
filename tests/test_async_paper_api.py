"""
验证异步论文上传和任务状态查询 API。
"""

from unittest.mock import patch

import fitz

from app.core.config import get_settings


def make_pdf() -> bytes:
    """生成包含文字的简单 PDF。"""

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Async paper processing test")

    data = pdf.tobytes()
    pdf.close()

    return data


def test_async_upload_returns_202(
    client,
    tmp_path,
    monkeypatch,
):
    """API 只创建任务，不等待 Worker 执行。"""

    monkeypatch.setattr(
        get_settings(),
        "UPLOAD_DIR",
        str(tmp_path),
    )

    # 避免单元测试连接真实 Redis。
    with patch(
        "app.api.papers.process_paper_task.apply_async"
    ) as send_task:

        response = client.post(
            "/papers/upload",
            files={
                "file": (
                    "async.pdf",
                    make_pdf(),
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 202

    data = response.json()

    assert data["status"] == "pending"
    assert data["task_id"]
    assert data["document_id"]

    # 验证派发参数与数据库任务 ID 一致。
    send_task.assert_called_once_with(
        args=[data["task_id"]],
        task_id=data["task_id"],
    )


def test_task_status_is_pending(
    client,
    tmp_path,
    monkeypatch,
):
    """没有 Worker 执行时，任务保持 pending。"""

    monkeypatch.setattr(
        get_settings(),
        "UPLOAD_DIR",
        str(tmp_path),
    )

    with patch(
        "app.api.papers.process_paper_task.apply_async"
    ):
        upload = client.post(
            "/papers/upload",
            files={
                "file": (
                    "async.pdf",
                    make_pdf(),
                    "application/pdf",
                )
            },
        )

    task_id = upload.json()["task_id"]

    response = client.get(f"/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["attempt_count"] == 0


def test_upload_reserves_dispatch_before_sending(
    client,
):
    """上传任务应先预留派发资格，再发送 Celery 消息。"""

    import fitz
    from unittest.mock import patch

    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Dispatch test")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    with patch(
        "app.api.papers.process_paper_task.apply_async"
    ) as dispatch:
        response = client.post(
            "/papers/upload",
            files={
                "file": (
                    "dispatch-test.pdf",
                    pdf_bytes,
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 202

    body = response.json()

    assert body["dispatch_status"] == "sent"

    dispatch.assert_called_once_with(
        args=[body["task_id"]],
        task_id=body["task_id"],
    )

def test_upload_dispatch_failure_keeps_pending(
    client,
    db_session,
):
    """派发失败时任务仍保留在数据库中等待恢复。"""

    import fitz
    from unittest.mock import patch

    from app.services.processing_job_repository import (
        ProcessingJobRepository,
    )

    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Redis failure test")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    with patch(
        "app.api.papers.process_paper_task.apply_async",
        side_effect=ConnectionError("Redis unavailable"),
    ):
        response = client.post(
            "/papers/upload",
            files={
                "file": (
                    "redis-failure.pdf",
                    pdf_bytes,
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 202

    body = response.json()
    assert body["dispatch_status"] == "deferred"

    db_session.expire_all()

    job = ProcessingJobRepository(db_session).get_by_task_id(
        body["task_id"]
    )

    assert job is not None
    assert job.status == "pending"
    assert job.next_dispatch_at is not None
