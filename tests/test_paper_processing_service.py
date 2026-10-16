"""
验证 PDF 重新解析后页面和 Chunk 的持久化结果。
"""

import fitz

from sqlalchemy import func, select

from app.models.document import Chunk, DocumentPage
from app.services.paper_processing_service import (
    PaperProcessingService,
)


def make_pdf() -> bytes:
    """生成两页文本型 PDF，避免测试依赖外部文件。"""

    pdf = fitz.open()

    for text in [
        "Introduction\n" + "Background text. " * 15,
        "Methods\n" + "Experiment details. " * 15,
    ]:
        page = pdf.new_page()

        page.insert_textbox(
            fitz.Rect(50, 50, 550, 750),
            text,
            fontsize=11,
        )

    data = pdf.tobytes()
    pdf.close()

    return data


def test_process_pdf_replaces_pages_and_chunks(
    db_session,
    sample_document,
):
    """重复处理同一文档，不应累积重复页面或 Chunk。"""

    service = PaperProcessingService(db_session)

    pdf_bytes = make_pdf()

    first_count = service.process_pdf(
        sample_document.id,
        pdf_bytes,
    )

    second_count = service.process_pdf(
        sample_document.id,
        pdf_bytes,
    )

    page_count = db_session.scalar(
        select(func.count())
        .select_from(DocumentPage)
        .where(
            DocumentPage.document_id == sample_document.id
        )
    )

    chunk_count = db_session.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(
            Chunk.document_id == sample_document.id
        )
    )

    assert page_count == 2
    assert chunk_count == first_count
    assert second_count == first_count
    assert chunk_count > 0
