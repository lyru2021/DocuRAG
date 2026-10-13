from typing import Annotated
from pathlib import Path



from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import get_settings
from app.services.paper_query_services import PaperQueryService
from app.services.file_storage import LocalFileStorage



router = APIRouter(prefix="/papers", tags=["Papers"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/{document_id}")
def get_paper(document_id: int, db: DbDep):
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
