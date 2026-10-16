"""原始 PDF 上传、下载和失败清理测试。"""

from unittest.mock import patch

import fitz
import pytest

from app.core.config import get_settings
from app.services.document_repository import DocumentRepository

def test_upload_and_download_original_pdf(
    client,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        get_settings(),
        "UPLOAD_DIR",
        str(tmp_path),
    )

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text(
        (72, 72),
        "Original PDF storage test",
    )

    content = pdf.tobytes()
    pdf.close()

    upload_response = client.post(
        "/documents/upload",
        files={
            "file": (
                "original.pdf",
                content,
                "application/pdf",
            )
        },
    )

    assert upload_response.status_code == 201

    document_id = upload_response.json()["id"]

    download_response = client.get(
        f"/papers/{document_id}/file"
    )

    assert download_response.status_code == 200
    assert download_response.content == content
    assert (
        download_response.headers["content-type"]
        == "application/pdf"
    )


def test_database_failure_cleans_up_pdf(
    client,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        get_settings(),
        "UPLOAD_DIR",
        str(tmp_path),
    )

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Rollback test")

    pdf_bytes = pdf.tobytes()
    pdf.close()

    with patch.object(
        DocumentRepository,
        "create_uploaded",
        side_effect=RuntimeError("Simulated DB failure"),
    ):
        with pytest.raises(
            RuntimeError,
            match="Simulated DB failure",
        ):
            client.post(
                "/documents/upload",
                files={
                    "file": (
                        "rollback.pdf",
                        pdf_bytes,
                        "application/pdf",
                    )
                },
            )

    assert list(tmp_path.glob("*.pdf")) == []
    assert list(tmp_path.glob(".upload-*.tmp")) == []
