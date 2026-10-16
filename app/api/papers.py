"""论文查询 API。

提供论文详情、页面、chunk、证据和原始 PDF 下载接口。
"""

from uuid import UUID
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session


from app.worker.paper_tasks import process_paper_task
from app.core.config import get_settings
from app.db.session import get_db
from app.services.file_storage import LocalFileStorage
from app.services.paper_query_services import PaperQueryService
from app.services.async_upload_service import AsyncUploadService
from app.services.processing_job_repository import ProcessingJobRepository

router = APIRouter(prefix="/papers", tags=["Papers"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/{document_id}")
def get_paper(document_id: int, db: DbDep):
    # 对外将缺失的文档统一表述为 Paper not found，避免暴露内部 Document 命名。
    service = PaperQueryService(db)

    document = service.get_document(document_id)

    if document is None:
        raise HTTPException(404, "Paper not found")

    metadata = service.get_metadata(document_id)

    return {
        "id": document.id,
        "filename": document.filename,
        "paper_title": (
            metadata.paper_title if metadata else None
        ),
        "authors": metadata.authors if metadata else None,
        "publication_year": (
            metadata.publication_year if metadata else None
        ),
        "doi": metadata.doi if metadata else None,
        "metadata_status": (
            metadata.metadata_status if metadata else "unverified"
        ),
    }


@router.get("/{document_id}/pages")
def get_paper_pages(document_id: int, db: DbDep):
    service = PaperQueryService(db)

    if service.get_document(document_id) is None:
        raise HTTPException(404, "Paper not found")

    pages = service.get_pages(document_id)

    return [
        {
            "page_number": page.page_number,
            "content": page.content,
            "start_char": page.start_char,
            "end_char": page.end_char,
        }
        for page in pages
    ]


@router.get("/{document_id}/chunks")
def get_paper_chunks(document_id: int, db: DbDep):
    service = PaperQueryService(db)

    if service.get_document(document_id) is None:
        raise HTTPException(404, "Paper not found")

    chunks = service.get_chunks(document_id)

    return [
        {
            "id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "start_char": chunk.start_char,
            "end_char": chunk.end_char,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
        }
        for chunk in chunks
    ]


@router.get("/{document_id}/evidence/{chunk_id}")
def get_chunk_evidence(
    document_id: int,
    chunk_id: int,
    db: DbDep,
):
    service = PaperQueryService(db)

    evidence = service.get_evidence(
        document_id,
        chunk_id,
    )

    if evidence is None:
        raise HTTPException(
            404,
            "Paper or chunk not found",
        )

    return evidence


@router.get("/{document_id}/file")
def get_original_pdf(
    document_id: int,
    db: DbDep,
):
    service = PaperQueryService(db)
    document = service.get_document(document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Paper not found",
        )

    if document.media_type != "application/pdf":
        raise HTTPException(
            status_code=404,
            detail="Original PDF not available",
        )

    if not document.file_id or not document.content_hash:
        raise HTTPException(
            status_code=404,
            detail="Original PDF not available",
        )

    storage = LocalFileStorage(Path(get_settings().UPLOAD_DIR))

    path = storage.get_pdf_path(document.file_id)

    if path is None:
        raise HTTPException(
            status_code=404,
            detail="Original PDF not found",
        )

    if not storage.verify_hash(
        document.file_id,
        document.content_hash,
    ):
        # hash 不一致说明文件内容可能被篡改或损坏，不能继续作为原始证据返回。
        raise HTTPException(
            status_code=409,
            detail="Original PDF hash mismatch",
        )

    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=document.filename,
        content_disposition_type="inline",
    )



@router.post("/upload", status_code=202)
async def upload_paper_async(
    db: DbDep,
    file: UploadFile = File(...),
):
    """接收 PDF，创建异步处理任务，立即返回任务 ID。"""

    filename = file.filename or "unnamed.pdf"

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=415,
            detail="Only PDF files are supported",
        )

    # 限制上传大小，避免一次读取无限大的文件。
    max_size = 10 * 1024 * 1024
    pdf_bytes = await file.read(max_size + 1)

    if len(pdf_bytes) > max_size:
        raise HTTPException(
            status_code=413,
            detail="PDF exceeds 10 MiB limit",
        )

    service = AsyncUploadService(db)

    try:
        document, task_id = service.create_paper_job(
            filename=filename,
            pdf_bytes=pdf_bytes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    # 数据库提交后，先原子预留派发资格。
    jobs = ProcessingJobRepository(db)

    try:
        reserved = jobs.reserve_dispatch(
            task_id=task_id,
            interval_seconds=30,
        )

        if not reserved:
            db.rollback()
            return {
                "document_id": document.id,
                "task_id": task_id,
                "status": "pending",
                "dispatch_status": "deferred",
            }

        # 预留必须先提交，其他调度器才能看到。
        db.commit()

    except Exception:
        db.rollback()

        # 任务已经创建成功，交给 Beat 后续恢复。
        return {
            "document_id": document.id,
            "task_id": task_id,
            "status": "pending",
            "dispatch_status": "deferred",
        }

    try:
        process_paper_task.apply_async(
            args=[task_id],
            task_id=task_id,
        )
    except Exception:
        # Redis 不可用时保留 pending，预留窗口结束后重新派发。
        return {
            "document_id": document.id,
            "task_id": task_id,
            "status": "pending",
            "dispatch_status": "deferred",
        }

    return {
        "document_id": document.id,
        "task_id": task_id,
        "status": "pending",
        "dispatch_status": "sent",
    }
